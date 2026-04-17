"use client";

import React, { useCallback, useEffect, useState, useTransition } from "react";
import Layout from "@/components/Layout";
import TenderTable from "@/components/tables/TenderTable";
import FilterPanel from "@/components/ui/FilterPanel";
import api from "@/lib/api";
import type { PaginatedResponse, TenderFilters, TenderListItem } from "@/types/tender";

const PAGE_SIZE = 25;
const DEFAULT_FILTERS: TenderFilters = { ordering: "-score", page: 1, page_size: PAGE_SIZE };

export default function TendersPage() {
  const [tenders, setTenders] = useState<TenderListItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [filters, setFilters] = useState<TenderFilters>(DEFAULT_FILTERS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [, startTransition] = useTransition();

  const fetchTenders = useCallback(async (f: TenderFilters) => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | number> = {};
      if (f.score_min) params.score_min = f.score_min;
      if (f.score_max) params.score_max = f.score_max;
      if (f.category) params.category = f.category;
      if (f.buyer_name) params.buyer_name = f.buyer_name;
      if (f.date_from) params.date_from = f.date_from;
      if (f.date_to) params.date_to = f.date_to;
      if (f.flag_type) params.flag_type = f.flag_type;
      if (f.ordering) params.ordering = f.ordering;
      params.page = f.page ?? 1;
      params.page_size = f.page_size ?? PAGE_SIZE;
      const { data } = await api.get<PaginatedResponse<TenderListItem>>("/tenders/", { params });
      setTenders(data.results);
      setTotalCount(data.count);
    } catch {
      setError("Failed to load tenders.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTenders(DEFAULT_FILTERS); }, [fetchTenders]);

  const handleFilterChange = useCallback((newFilters: Partial<TenderFilters>) => {
    startTransition(() => {
      const updated: TenderFilters = { ...filters, ...newFilters, page: 1 };
      setFilters(updated);
      fetchTenders(updated);
    });
  }, [filters, fetchTenders]);

  const handlePageChange = useCallback((page: number) => {
    const updated = { ...filters, page };
    setFilters(updated);
    fetchTenders(updated);
  }, [filters, fetchTenders]);

  const handleSortChange = useCallback((ordering: string) => {
    const updated: TenderFilters = { ...filters, ordering, page: 1 };
    setFilters(updated);
    fetchTenders(updated);
  }, [filters, fetchTenders]);

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 style={{ color: "var(--text-primary)", fontWeight: 700, fontSize: "1.25rem", letterSpacing: "-0.02em" }}>
              Tenders
            </h1>
            <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginTop: "0.2rem" }}>
              All procurement tenders with fraud risk scores
            </p>
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="ts-btn ts-btn-ghost xl:hidden"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
            </svg>
            Filters
          </button>
        </div>

        <div className="flex flex-col xl:flex-row gap-5">
          <aside className={`xl:w-60 shrink-0 ${showFilters ? "block" : "hidden xl:block"}`}>
            <FilterPanel filters={filters} onFilterChange={handleFilterChange} />
          </aside>
          <div className="flex-1 min-w-0">
            {error ? (
              <div className="flex items-center justify-between px-4 py-3 rounded-xl text-sm"
                style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)", color: "#fca5a5" }}>
                <span>{error}</span>
                <button onClick={() => fetchTenders(filters)} className="ts-btn ts-btn-ghost text-xs px-3 py-1"
                  style={{ color: "#fca5a5", borderColor: "rgba(239,68,68,0.3)" }}>Retry</button>
              </div>
            ) : (
              <TenderTable tenders={tenders} loading={loading} totalCount={totalCount}
                currentPage={filters.page ?? 1} totalPages={totalPages}
                ordering={filters.ordering ?? "-score"}
                onPageChange={handlePageChange} onSortChange={handleSortChange} />
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
}
