// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import HomePage from "../app/page";

test("the landing page names the project and states its purpose", () => {
  render(<HomePage />);

  const main = screen.getByRole("main");
  expect(within(main).getByRole("heading", { level: 1 }).textContent).toBe("Influence Graph");
  const purpose = within(main).getByText(
    "Influence Graph scores how likely an EU amendment was written from a lobby submission, maps who wins, and predicts which consultation proposals reach the final law.",
  );
  expect(purpose.tagName).toBe("P");
});
