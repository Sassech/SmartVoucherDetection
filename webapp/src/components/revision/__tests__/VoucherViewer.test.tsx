/**
 * VoucherViewer tests — R-43, S-33, 4.D.14
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { VoucherViewer } from "../VoucherViewer";

describe("VoucherViewer", () => {
  it("renders img with correct src (S-33)", () => {
    render(<VoucherViewer src="https://example.com/voucher.jpg" />);
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", "https://example.com/voucher.jpg");
  });

  it("renders Skeleton before image loads", () => {
    render(<VoucherViewer src="https://example.com/voucher.jpg" />);
    // Skeleton visible while image has not fired onLoad
    expect(screen.getByTestId("voucher-skeleton")).toBeInTheDocument();
  });

  it("renders alt text on the image", () => {
    render(<VoucherViewer src="https://example.com/img.png" alt="mi comprobante" />);
    expect(screen.getByRole("img")).toHaveAttribute("alt", "mi comprobante");
  });

  it("uses default alt text when not provided", () => {
    render(<VoucherViewer src="https://example.com/img.png" />);
    expect(screen.getByRole("img")).toHaveAttribute("alt", "comprobante");
  });

  it("hides skeleton after image loads", () => {
    render(<VoucherViewer src="https://example.com/voucher.jpg" />);
    const img = screen.getByRole("img");
    fireEvent.load(img);
    expect(screen.queryByTestId("voucher-skeleton")).not.toBeInTheDocument();
  });

  it("renders placeholder message when src is null", () => {
    render(<VoucherViewer src={null} />);
    expect(screen.getByText(/sin imagen/i)).toBeInTheDocument();
  });
});
