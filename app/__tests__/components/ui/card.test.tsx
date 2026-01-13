import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";

describe("Card Components", () => {
  describe("Card", () => {
    it("should render with children", () => {
      render(<Card>Card content</Card>);

      expect(screen.getByText("Card content")).toBeInTheDocument();
    });

    it("should apply base styles", () => {
      render(<Card data-testid="card">Content</Card>);

      const card = screen.getByTestId("card");
      expect(card).toHaveClass("rounded-lg");
      expect(card).toHaveClass("border");
      expect(card).toHaveClass("bg-card");
      expect(card).toHaveClass("shadow-sm");
    });

    it("should accept custom className", () => {
      render(
        <Card className="custom-class" data-testid="card">
          Content
        </Card>
      );

      expect(screen.getByTestId("card")).toHaveClass("custom-class");
    });

    it("should forward ref correctly", () => {
      const ref = vi.fn();
      render(<Card ref={ref}>Content</Card>);

      expect(ref).toHaveBeenCalled();
      expect(ref.mock.calls[0][0]).toBeInstanceOf(HTMLDivElement);
    });

    it("should spread additional props", () => {
      render(
        <Card data-testid="card" aria-label="Card container">
          Content
        </Card>
      );

      expect(screen.getByLabelText("Card container")).toBeInTheDocument();
    });

    it("should render as div element", () => {
      render(<Card data-testid="card">Content</Card>);

      expect(screen.getByTestId("card").tagName).toBe("DIV");
    });
  });

  describe("CardHeader", () => {
    it("should render with children", () => {
      render(<CardHeader>Header content</CardHeader>);

      expect(screen.getByText("Header content")).toBeInTheDocument();
    });

    it("should apply flex column styles", () => {
      render(<CardHeader data-testid="header">Header</CardHeader>);

      const header = screen.getByTestId("header");
      expect(header).toHaveClass("flex");
      expect(header).toHaveClass("flex-col");
      expect(header).toHaveClass("space-y-1.5");
    });

    it("should apply padding", () => {
      render(<CardHeader data-testid="header">Header</CardHeader>);

      expect(screen.getByTestId("header")).toHaveClass("p-6");
    });

    it("should accept custom className", () => {
      render(
        <CardHeader className="extra-padding" data-testid="header">
          Header
        </CardHeader>
      );

      expect(screen.getByTestId("header")).toHaveClass("extra-padding");
    });

    it("should forward ref correctly", () => {
      const ref = vi.fn();
      render(<CardHeader ref={ref}>Header</CardHeader>);

      expect(ref).toHaveBeenCalled();
      expect(ref.mock.calls[0][0]).toBeInstanceOf(HTMLDivElement);
    });
  });

  describe("CardTitle", () => {
    it("should render with children", () => {
      render(<CardTitle>Card Title</CardTitle>);

      expect(screen.getByText("Card Title")).toBeInTheDocument();
    });

    it("should render as h3 element", () => {
      render(<CardTitle data-testid="title">Title</CardTitle>);

      expect(screen.getByTestId("title").tagName).toBe("H3");
    });

    it("should apply typography styles", () => {
      render(<CardTitle data-testid="title">Title</CardTitle>);

      const title = screen.getByTestId("title");
      expect(title).toHaveClass("text-2xl");
      expect(title).toHaveClass("font-semibold");
      expect(title).toHaveClass("leading-none");
      expect(title).toHaveClass("tracking-tight");
    });

    it("should accept custom className", () => {
      render(
        <CardTitle className="text-red-500" data-testid="title">
          Title
        </CardTitle>
      );

      expect(screen.getByTestId("title")).toHaveClass("text-red-500");
    });

    it("should forward ref correctly", () => {
      const ref = vi.fn();
      render(<CardTitle ref={ref}>Title</CardTitle>);

      expect(ref).toHaveBeenCalled();
    });

    it("should be accessible as heading", () => {
      render(<CardTitle>Accessible Title</CardTitle>);

      expect(screen.getByRole("heading", { name: "Accessible Title" })).toBeInTheDocument();
    });
  });

  describe("CardDescription", () => {
    it("should render with children", () => {
      render(<CardDescription>Description text</CardDescription>);

      expect(screen.getByText("Description text")).toBeInTheDocument();
    });

    it("should render as p element", () => {
      render(<CardDescription data-testid="desc">Description</CardDescription>);

      expect(screen.getByTestId("desc").tagName).toBe("P");
    });

    it("should apply muted text styles", () => {
      render(<CardDescription data-testid="desc">Description</CardDescription>);

      const desc = screen.getByTestId("desc");
      expect(desc).toHaveClass("text-sm");
      expect(desc).toHaveClass("text-muted-foreground");
    });

    it("should accept custom className", () => {
      render(
        <CardDescription className="italic" data-testid="desc">
          Description
        </CardDescription>
      );

      expect(screen.getByTestId("desc")).toHaveClass("italic");
    });

    it("should forward ref correctly", () => {
      const ref = vi.fn();
      render(<CardDescription ref={ref}>Description</CardDescription>);

      expect(ref).toHaveBeenCalled();
      expect(ref.mock.calls[0][0]).toBeInstanceOf(HTMLParagraphElement);
    });
  });

  describe("CardContent", () => {
    it("should render with children", () => {
      render(<CardContent>Content goes here</CardContent>);

      expect(screen.getByText("Content goes here")).toBeInTheDocument();
    });

    it("should apply padding styles", () => {
      render(<CardContent data-testid="content">Content</CardContent>);

      const content = screen.getByTestId("content");
      expect(content).toHaveClass("p-6");
      expect(content).toHaveClass("pt-0");
    });

    it("should accept custom className", () => {
      render(
        <CardContent className="bg-gray-100" data-testid="content">
          Content
        </CardContent>
      );

      expect(screen.getByTestId("content")).toHaveClass("bg-gray-100");
    });

    it("should forward ref correctly", () => {
      const ref = vi.fn();
      render(<CardContent ref={ref}>Content</CardContent>);

      expect(ref).toHaveBeenCalled();
      expect(ref.mock.calls[0][0]).toBeInstanceOf(HTMLDivElement);
    });
  });

  describe("CardFooter", () => {
    it("should render with children", () => {
      render(<CardFooter>Footer content</CardFooter>);

      expect(screen.getByText("Footer content")).toBeInTheDocument();
    });

    it("should apply flex layout styles", () => {
      render(<CardFooter data-testid="footer">Footer</CardFooter>);

      const footer = screen.getByTestId("footer");
      expect(footer).toHaveClass("flex");
      expect(footer).toHaveClass("items-center");
    });

    it("should apply padding styles", () => {
      render(<CardFooter data-testid="footer">Footer</CardFooter>);

      const footer = screen.getByTestId("footer");
      expect(footer).toHaveClass("p-6");
      expect(footer).toHaveClass("pt-0");
    });

    it("should accept custom className", () => {
      render(
        <CardFooter className="justify-between" data-testid="footer">
          Footer
        </CardFooter>
      );

      expect(screen.getByTestId("footer")).toHaveClass("justify-between");
    });

    it("should forward ref correctly", () => {
      const ref = vi.fn();
      render(<CardFooter ref={ref}>Footer</CardFooter>);

      expect(ref).toHaveBeenCalled();
      expect(ref.mock.calls[0][0]).toBeInstanceOf(HTMLDivElement);
    });
  });

  describe("Card composition", () => {
    it("should render complete card with all subcomponents", () => {
      render(
        <Card data-testid="card">
          <CardHeader>
            <CardTitle>Test Card</CardTitle>
            <CardDescription>A test card description</CardDescription>
          </CardHeader>
          <CardContent>
            <p>Card body content</p>
          </CardContent>
          <CardFooter>
            <button>Action</button>
          </CardFooter>
        </Card>
      );

      expect(screen.getByTestId("card")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "Test Card" })).toBeInTheDocument();
      expect(screen.getByText("A test card description")).toBeInTheDocument();
      expect(screen.getByText("Card body content")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Action" })).toBeInTheDocument();
    });

    it("should allow nested elements in card content", () => {
      render(
        <Card>
          <CardContent>
            <div data-testid="nested">
              <span>Nested content</span>
            </div>
          </CardContent>
        </Card>
      );

      expect(screen.getByTestId("nested")).toBeInTheDocument();
      expect(screen.getByText("Nested content")).toBeInTheDocument();
    });

    it("should allow custom content without subcomponents", () => {
      render(
        <Card>
          <div className="p-4">
            <h4>Custom Layout</h4>
            <p>Without using card subcomponents</p>
          </div>
        </Card>
      );

      expect(screen.getByText("Custom Layout")).toBeInTheDocument();
      expect(screen.getByText("Without using card subcomponents")).toBeInTheDocument();
    });
  });

  describe("displayName", () => {
    it("should have correct displayName for Card", () => {
      expect(Card.displayName).toBe("Card");
    });

    it("should have correct displayName for CardHeader", () => {
      expect(CardHeader.displayName).toBe("CardHeader");
    });

    it("should have correct displayName for CardTitle", () => {
      expect(CardTitle.displayName).toBe("CardTitle");
    });

    it("should have correct displayName for CardDescription", () => {
      expect(CardDescription.displayName).toBe("CardDescription");
    });

    it("should have correct displayName for CardContent", () => {
      expect(CardContent.displayName).toBe("CardContent");
    });

    it("should have correct displayName for CardFooter", () => {
      expect(CardFooter.displayName).toBe("CardFooter");
    });
  });
});
