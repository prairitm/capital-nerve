import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { BackButton } from "@/components/common/BackButton";

afterEach(cleanup);

function CurrentPath() {
  return <output aria-label="Current path">{useLocation().pathname}</output>;
}

describe("BackButton", () => {
  it("returns to the previous route when in-app history exists", () => {
    render(
      <MemoryRouter
        initialEntries={["/companies", "/company/RELIANCE"]}
        initialIndex={1}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <BackButton fallback="/fallback" />
        <CurrentPath />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Back" }));

    expect(screen.getByLabelText("Current path")).toHaveTextContent("/companies");
  });

  it("uses the fallback route when the page was opened directly", () => {
    render(
      <MemoryRouter
        initialEntries={["/company/RELIANCE/event/event-1"]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <BackButton fallback="/company/RELIANCE/events" />
        <CurrentPath />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Back" }));

    expect(screen.getByLabelText("Current path")).toHaveTextContent(
      "/company/RELIANCE/events",
    );
  });
});
