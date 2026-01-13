import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button, buttonVariants } from "@/components/ui/button";
import { Loader2 } from "lucide-react";

describe("Button", () => {
  describe("rendering", () => {
    it("should render with children", () => {
      render(<Button>Click me</Button>);

      expect(screen.getByRole("button", { name: /click me/i })).toBeInTheDocument();
    });

    it("should render as button element by default", () => {
      render(<Button>Click me</Button>);

      const button = screen.getByRole("button");
      expect(button.tagName).toBe("BUTTON");
    });

    it("should forward ref correctly", () => {
      const ref = vi.fn();
      render(<Button ref={ref}>Click me</Button>);

      expect(ref).toHaveBeenCalled();
      expect(ref.mock.calls[0][0]).toBeInstanceOf(HTMLButtonElement);
    });

    it("should accept custom className", () => {
      render(<Button className="custom-class">Click me</Button>);

      const button = screen.getByRole("button");
      expect(button).toHaveClass("custom-class");
    });

    it("should spread additional props", () => {
      render(
        <Button data-testid="custom-button" aria-label="Custom label">
          Click me
        </Button>
      );

      expect(screen.getByTestId("custom-button")).toBeInTheDocument();
      expect(screen.getByLabelText("Custom label")).toBeInTheDocument();
    });
  });

  describe("variants", () => {
    it("should apply default variant styles", () => {
      render(<Button>Default</Button>);

      const button = screen.getByRole("button");
      expect(button).toHaveClass("bg-primary");
      expect(button).toHaveClass("text-primary-foreground");
    });

    it("should apply destructive variant styles", () => {
      render(<Button variant="destructive">Delete</Button>);

      const button = screen.getByRole("button");
      expect(button).toHaveClass("bg-destructive");
      expect(button).toHaveClass("text-destructive-foreground");
    });

    it("should apply outline variant styles", () => {
      render(<Button variant="outline">Outline</Button>);

      const button = screen.getByRole("button");
      expect(button).toHaveClass("border");
      expect(button).toHaveClass("bg-background");
    });

    it("should apply secondary variant styles", () => {
      render(<Button variant="secondary">Secondary</Button>);

      const button = screen.getByRole("button");
      expect(button).toHaveClass("bg-secondary");
      expect(button).toHaveClass("text-secondary-foreground");
    });

    it("should apply ghost variant styles", () => {
      render(<Button variant="ghost">Ghost</Button>);

      const button = screen.getByRole("button");
      expect(button).toHaveClass("hover:bg-accent");
    });

    it("should apply link variant styles", () => {
      render(<Button variant="link">Link</Button>);

      const button = screen.getByRole("button");
      expect(button).toHaveClass("text-primary");
      expect(button).toHaveClass("underline-offset-4");
    });
  });

  describe("sizes", () => {
    it("should apply default size", () => {
      render(<Button>Default size</Button>);

      const button = screen.getByRole("button");
      expect(button).toHaveClass("h-10");
      expect(button).toHaveClass("px-4");
      expect(button).toHaveClass("py-2");
    });

    it("should apply small size", () => {
      render(<Button size="sm">Small</Button>);

      const button = screen.getByRole("button");
      expect(button).toHaveClass("h-9");
      expect(button).toHaveClass("px-3");
    });

    it("should apply large size", () => {
      render(<Button size="lg">Large</Button>);

      const button = screen.getByRole("button");
      expect(button).toHaveClass("h-11");
      expect(button).toHaveClass("px-8");
    });

    it("should apply icon size", () => {
      render(<Button size="icon">X</Button>);

      const button = screen.getByRole("button");
      expect(button).toHaveClass("h-10");
      expect(button).toHaveClass("w-10");
    });
  });

  describe("interaction", () => {
    it("should handle click events", async () => {
      const handleClick = vi.fn();
      const user = userEvent.setup();

      render(<Button onClick={handleClick}>Click me</Button>);

      await user.click(screen.getByRole("button"));

      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it("should not trigger click when disabled", async () => {
      const handleClick = vi.fn();
      const user = userEvent.setup();

      render(
        <Button onClick={handleClick} disabled>
          Click me
        </Button>
      );

      const button = screen.getByRole("button");
      await user.click(button);

      expect(handleClick).not.toHaveBeenCalled();
    });

    it("should apply disabled styles when disabled", () => {
      render(<Button disabled>Disabled</Button>);

      const button = screen.getByRole("button");
      expect(button).toBeDisabled();
      expect(button).toHaveClass("disabled:pointer-events-none");
      expect(button).toHaveClass("disabled:opacity-50");
    });

    it("should support keyboard interaction", async () => {
      const handleClick = vi.fn();
      const user = userEvent.setup();

      render(<Button onClick={handleClick}>Press me</Button>);

      const button = screen.getByRole("button");
      button.focus();
      await user.keyboard("{Enter}");

      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it("should support space key activation", async () => {
      const handleClick = vi.fn();
      const user = userEvent.setup();

      render(<Button onClick={handleClick}>Press me</Button>);

      const button = screen.getByRole("button");
      button.focus();
      await user.keyboard(" ");

      expect(handleClick).toHaveBeenCalledTimes(1);
    });
  });

  describe("loading state", () => {
    it("should render with loading spinner", () => {
      render(
        <Button disabled>
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          Loading...
        </Button>
      );

      expect(screen.getByRole("button")).toHaveTextContent("Loading...");
      expect(screen.getByRole("button")).toBeDisabled();
    });

    it("should be disabled while loading", () => {
      render(
        <Button disabled>
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          Saving...
        </Button>
      );

      expect(screen.getByRole("button")).toBeDisabled();
    });
  });

  describe("asChild prop", () => {
    it("should render as custom element when asChild is true", () => {
      render(
        <Button asChild>
          <a href="/test">Link Button</a>
        </Button>
      );

      const link = screen.getByRole("link", { name: /link button/i });
      expect(link).toBeInTheDocument();
      expect(link.tagName).toBe("A");
      expect(link).toHaveAttribute("href", "/test");
    });

    it("should apply button styles to child element", () => {
      render(
        <Button asChild variant="destructive">
          <a href="/delete">Delete</a>
        </Button>
      );

      const link = screen.getByRole("link");
      expect(link).toHaveClass("bg-destructive");
    });
  });

  describe("buttonVariants utility", () => {
    it("should generate correct class string for default variant", () => {
      const classes = buttonVariants({ variant: "default" });

      expect(classes).toContain("bg-primary");
    });

    it("should generate correct class string for custom variant and size", () => {
      const classes = buttonVariants({ variant: "outline", size: "lg" });

      expect(classes).toContain("border");
      expect(classes).toContain("h-11");
    });

    it("should include base classes", () => {
      const classes = buttonVariants();

      expect(classes).toContain("inline-flex");
      expect(classes).toContain("items-center");
      expect(classes).toContain("justify-center");
    });
  });

  describe("focus states", () => {
    it("should have focus-visible ring styles", () => {
      render(<Button>Focusable</Button>);

      const button = screen.getByRole("button");
      expect(button).toHaveClass("focus-visible:outline-none");
      expect(button).toHaveClass("focus-visible:ring-2");
      expect(button).toHaveClass("focus-visible:ring-ring");
    });
  });

  describe("accessibility", () => {
    it("should be focusable", () => {
      render(<Button>Accessible</Button>);

      const button = screen.getByRole("button");
      button.focus();

      expect(document.activeElement).toBe(button);
    });

    it("should support aria-label", () => {
      render(<Button aria-label="Close dialog">X</Button>);

      expect(screen.getByLabelText("Close dialog")).toBeInTheDocument();
    });

    it("should support aria-disabled", () => {
      render(<Button aria-disabled="true">Cannot click</Button>);

      expect(screen.getByRole("button")).toHaveAttribute("aria-disabled", "true");
    });

    it("should have correct type attribute", () => {
      render(<Button>Submit</Button>);

      // Buttons without explicit type should not have type set
      // which means they default to "submit" in forms
      const button = screen.getByRole("button");
      expect(button).not.toHaveAttribute("type");
    });

    it("should support explicit type attribute", () => {
      render(<Button type="submit">Submit</Button>);

      expect(screen.getByRole("button")).toHaveAttribute("type", "submit");
    });
  });

  describe("displayName", () => {
    it("should have correct displayName for debugging", () => {
      expect(Button.displayName).toBe("Button");
    });
  });
});
