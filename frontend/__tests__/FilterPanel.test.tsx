/**
 * Unit tests for FilterPanel component.
 * Validates: Requirement 9.2 (filter controls), Requirement 9.3 (update within 1s).
 */
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FilterPanel from "@/components/ui/FilterPanel";
import type { TenderFilters } from "@/types/tender";

const emptyFilters: TenderFilters = {};

describe("FilterPanel", () => {
  it("renders all filter controls", () => {
    render(<FilterPanel filters={emptyFilters} onFilterChange={jest.fn()} />);
    expect(screen.getByLabelText(/minimum risk score/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/maximum risk score/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/filter by category/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/filter by buyer name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/deadline from date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/deadline to date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/filter by red flag type/i)).toBeInTheDocument();
  });

  it("does not show 'Clear all' when no filters active", () => {
    render(<FilterPanel filters={emptyFilters} onFilterChange={jest.fn()} />);
    expect(screen.queryByText(/clear all/i)).not.toBeInTheDocument();
  });

  it("shows 'Clear all' when a filter is active", async () => {
    render(<FilterPanel filters={{ category: "Construction" }} onFilterChange={jest.fn()} />);
    expect(screen.getByText(/clear all/i)).toBeInTheDocument();
  });

  it("calls onFilterChange with category value (debounced)", async () => {
    jest.useFakeTimers();
    const onChange = jest.fn();
    render(<FilterPanel filters={emptyFilters} onFilterChange={onChange} />);

    const input = screen.getByLabelText(/filter by category/i);
    fireEvent.change(input, { target: { value: "Roads" } });

    // Should not fire immediately
    expect(onChange).not.toHaveBeenCalled();

    // After debounce delay
    jest.advanceTimersByTime(500);
    expect(onChange).toHaveBeenCalledWith({ category: "Roads" });
    jest.useRealTimers();
  });

  it("calls onFilterChange immediately on flag type select change", () => {
    const onChange = jest.fn();
    render(<FilterPanel filters={emptyFilters} onFilterChange={onChange} />);

    const select = screen.getByLabelText(/filter by red flag type/i);
    fireEvent.change(select, { target: { value: "SINGLE_BIDDER" } });

    expect(onChange).toHaveBeenCalledWith({ flag_type: "SINGLE_BIDDER" });
  });

  it("calls onFilterChange immediately on date change", () => {
    const onChange = jest.fn();
    render(<FilterPanel filters={emptyFilters} onFilterChange={onChange} />);

    const dateInput = screen.getByLabelText(/deadline from date/i);
    fireEvent.change(dateInput, { target: { value: "2024-01-01" } });

    expect(onChange).toHaveBeenCalledWith({ date_from: "2024-01-01" });
  });

  it("resets all filters on 'Clear all' click", () => {
    const onChange = jest.fn();
    render(
      <FilterPanel
        filters={{ category: "Roads", flag_type: "SINGLE_BIDDER" }}
        onFilterChange={onChange}
      />
    );

    fireEvent.click(screen.getByText(/clear all/i));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        category: undefined,
        flag_type: undefined,
        score_min: undefined,
        score_max: undefined,
        buyer_name: undefined,
        date_from: undefined,
        date_to: undefined,
      })
    );
  });

  it("renders all flag type options in the select", () => {
    render(<FilterPanel filters={emptyFilters} onFilterChange={jest.fn()} />);
    const select = screen.getByLabelText(/filter by red flag type/i) as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toContain("SINGLE_BIDDER");
    expect(options).toContain("PRICE_ANOMALY");
    expect(options).toContain("REPEAT_WINNER");
    expect(options).toContain("SHORT_DEADLINE");
    expect(options).toContain("LINKED_ENTITIES");
    expect(options).toContain("COVER_BID_PATTERN");
  });

  it("calls onFilterChange with undefined when score_min is cleared", async () => {
    jest.useFakeTimers();
    const onChange = jest.fn();
    render(<FilterPanel filters={{ score_min: "50" }} onFilterChange={onChange} />);

    const input = screen.getByLabelText(/minimum risk score/i);
    fireEvent.change(input, { target: { value: "" } });
    jest.advanceTimersByTime(500);

    expect(onChange).toHaveBeenCalledWith({ score_min: undefined });
    jest.useRealTimers();
  });
});
