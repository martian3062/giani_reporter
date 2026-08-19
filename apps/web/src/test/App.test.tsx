import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import App from "../App";
import { DeskProvider } from "../DeskContext";

const renderRoute = (route: string) =>
  render(
    <MemoryRouter initialEntries={[route]}>
      <DeskProvider>
        <App />
      </DeskProvider>
    </MemoryRouter>,
  );

describe("Signal Desk smoke routes", () => {
  it("renders the overview with the canonical Mira identity", () => {
    renderRoute("/");

    expect(
      screen.getByRole("heading", {
        name: /good evening\. the desk is live\./i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /mira, the giani ai news anchor/i }),
    ).toHaveAttribute("src", "/anchor/mira-anchor-vertical.png");
    expect(screen.getByText(/3\/3 locked/i)).toBeInTheDocument();
  });

  it("keeps the daily rundown capped at exactly three stories", async () => {
    const user = userEvent.setup();
    renderRoute("/research");

    expect(
      screen.getByRole("heading", { name: /find the signal/i }),
    ).toBeInTheDocument();

    await user.click(
      screen.getAllByRole("button", { name: /add to rundown/i })[0],
    );

    expect(
      await screen.findByText(
        /the rundown is full\. deselect one story before adding another/i,
      ),
    ).toBeInTheDocument();
  });

  it("blocks script generation when the human angle is empty", async () => {
    const user = userEvent.setup();
    renderRoute("/studio");

    const angle = screen.getByRole("textbox", {
      name: /one-sentence angle/i,
    });
    await user.clear(angle);
    await user.click(
      screen.getByRole("button", { name: /generate structured draft/i }),
    );

    expect(
      await screen.findByText(/the angle must be one complete sentence/i),
    ).toBeInTheDocument();
  });
});
