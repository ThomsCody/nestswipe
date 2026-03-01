import base64
import json
import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

BATCH_SIZE = 5

SYSTEM_PROMPT = """You are a photo classifier for real estate listings.
For each image, determine if it shows the actual property being sold.

Return a JSON object with a single key "keep" containing an array of booleans,
one per image in the same order they were provided.

Answer true for: property interior rooms, exterior/facade, balcony, terrace,
view from the property, building entrance, garden, parking space, common areas.

Answer false for: real estate agent portraits, agency logos, maps, floor plans,
neighborhood overview photos, energy performance labels, promotional banners,
QR codes, contact cards, watermark-only images."""


def _image_to_data_url(image_bytes: bytes) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    return f"data:image/jpeg;base64,{b64}"


async def _classify_batch(
    client: AsyncOpenAI,
    batch: list[tuple[bytes, str | None, str]],
) -> list[bool]:
    """Classify a batch of photos, return list of booleans."""
    content: list[dict] = [
        {"type": "text", "text": f"Classify these {len(batch)} images:"}
    ]
    for img_bytes, _, _ in batch:
        content.append({
            "type": "image_url",
            "image_url": {"url": _image_to_data_url(img_bytes), "detail": "low"},
        })

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0,
    )

    data = json.loads(response.choices[0].message.content)
    results = data.get("keep", [])

    # Sanity check: if the model returned wrong length, keep all photos
    if len(results) != len(batch):
        logger.warning(
            "Classifier returned %d results for %d photos, keeping all",
            len(results), len(batch),
        )
        return [True] * len(batch)

    return results


async def classify_photos(
    api_key: str,
    photos: list[tuple[bytes, str | None, str]],
) -> list[tuple[bytes, str | None, str]]:
    """
    Filter out non-property photos using GPT-4o-mini vision.

    Takes and returns the same (img_bytes, phash, url) tuple format
    used by email_processor.py.
    """
    if not photos:
        return photos

    client = AsyncOpenAI(api_key=api_key)
    keep_flags: list[bool] = []

    # Process in batches
    for i in range(0, len(photos), BATCH_SIZE):
        batch = photos[i : i + BATCH_SIZE]
        try:
            flags = await _classify_batch(client, batch)
            keep_flags.extend(flags)
        except Exception:
            logger.exception("Photo classification failed for batch %d, keeping all", i)
            keep_flags.extend([True] * len(batch))

    filtered = [photo for photo, keep in zip(photos, keep_flags) if keep]
    removed = len(photos) - len(filtered)
    if removed:
        logger.info("Photo classifier: kept %d/%d photos (removed %d)", len(filtered), len(photos), removed)

    return filtered
