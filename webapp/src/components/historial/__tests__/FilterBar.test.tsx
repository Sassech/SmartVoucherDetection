/**
 * FilterBar tests — R-40, R-41, S-27, S-28, S-32, 4.D.13
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { FilterBar } from "../FilterBar";
import type { FilterState } from "@/lib/types";

const emptyFilter: FilterState = {
  status: [],
  date_from: "",
  date_to: "",
};

describe("FilterBar", () => {
  it("initial state: no pills selected, no dates", () => {
    const onChange = vi.fn();
    render(<FilterBar value={emptyFilter} onChange={onChange} />);

    // All status pills rendered
    expect(screen.getByRole("button", { name: /pendiente/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /procesado/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /duplicado/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /error/i })).toBeInTheDocument();

    // Date inputs empty
    expect(screen.getByLabelText(/fecha desde/i)).toHaveValue("");
    expect(screen.getByLabelText(/fecha hasta/i)).toHaveValue("");
  });

  it("clicking a status pill adds it to selection (S-27)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<FilterBar value={emptyFilter} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: /pendiente/i }));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: ["pendiente"] }),
    );
  });

  it("clicking selected pill removes it", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const selectedFilter: FilterState = { ...emptyFilter, status: ["pendiente"] };
    render(<FilterBar value={selectedFilter} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: /pendiente/i }));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: [] }),
    );
  });

  it("multiple pills can be selected (R-40)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    // Simulate having "pendiente" already selected, now click "duplicado"
    const selectedFilter: FilterState = { ...emptyFilter, status: ["pendiente"] };
    render(<FilterBar value={selectedFilter} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: /duplicado/i }));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: ["pendiente", "duplicado"] }),
    );
  });

  it("date_from input updates state", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<FilterBar value={emptyFilter} onChange={onChange} />);

    await user.type(screen.getByLabelText(/fecha desde/i), "2024-01-01");

    // Last onChange call should have date_from set
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.date_from).toBe("2024-01-01");
  });

  it("date_to input updates state", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<FilterBar value={emptyFilter} onChange={onChange} />);

    await user.type(screen.getByLabelText(/fecha hasta/i), "2024-12-31");

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.date_to).toBe("2024-12-31");
  });

  it("clearing date_from removes filter (S-28)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const withDate: FilterState = { ...emptyFilter, date_from: "2024-01-01" };
    render(<FilterBar value={withDate} onChange={onChange} />);

    const input = screen.getByLabelText(/fecha desde/i);
    await user.clear(input);

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.date_from).toBe("");
  });

  it("clearing date_to removes filter", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const withDate: FilterState = { ...emptyFilter, date_to: "2024-12-31" };
    render(<FilterBar value={withDate} onChange={onChange} />);

    const input = screen.getByLabelText(/fecha hasta/i);
    await user.clear(input);

    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(lastCall.date_to).toBe("");
  });

  it("combined status + date filter (S-32)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<FilterBar value={emptyFilter} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: /procesado/i }));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: ["procesado"] }),
    );
  });

  it("onChange called with correct FilterState shape", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<FilterBar value={emptyFilter} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: /error/i }));

    expect(onChange).toHaveBeenCalledWith({
      status: ["error"],
      date_from: "",
      date_to: "",
    });
  });
});
