import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ErrorBox from "./ErrorBox";

describe("ErrorBox", () => {
  it("renders default message when none is provided", () => {
    render(<ErrorBox />);
    expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
  });

  it("renders custom message", () => {
    render(<ErrorBox message="Network error" />);
    expect(screen.getByText("Network error")).toBeInTheDocument();
  });

  it("shows retry button when onRetry is provided", () => {
    render(<ErrorBox onRetry={() => {}} />);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("hides retry button when onRetry is not provided", () => {
    render(<ErrorBox />);
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("calls onRetry when retry button is clicked", async () => {
    const onRetry = vi.fn();
    render(<ErrorBox onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
