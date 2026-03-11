interface OwnerAvatarProps {
  name: string;
  picture?: string | null;
  size?: "sm" | "md";
}

export default function OwnerAvatar({ name, picture, size = "sm" }: OwnerAvatarProps) {
  const px = size === "sm" ? "w-6 h-6 text-[10px]" : "w-8 h-8 text-xs";
  const initials = name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  if (picture) {
    return <img src={picture} alt={name} className={`${px} rounded-full object-cover`} />;
  }
  return (
    <span className={`${px} rounded-full bg-gray-300 text-white flex items-center justify-center font-medium`}>
      {initials}
    </span>
  );
}
