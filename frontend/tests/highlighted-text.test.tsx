// @vitest-environment jsdom
import { render } from "@testing-library/react";
import { expect, test } from "vitest";
import { HighlightedText } from "../components/highlighted-text";

test("evidence offsets count Unicode characters after an emoji", () => {
  const { container } = render(
    <HighlightedText text="A😀B" spans={[{ start: 2, end: 3, text: "B" }]} />,
  );

  expect(container.textContent).toBe("A😀B");
  expect(container.querySelector("mark")?.textContent).toBe("B");
});
