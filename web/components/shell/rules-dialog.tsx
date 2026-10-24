"use client";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SeverityPill, Tag } from "@/components/ui/pill";
import { CATEGORIES, RULES } from "@/lib/rules";

/**
 * The six checks, read only. They are deterministic code in rules/checks.py,
 * not settings, so this explains them rather than pretending to configure.
 */
export function RulesDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>The six checks</DialogTitle>
          <DialogDescription>
            Plain code, not a model, so the same workbook always gets the same findings. Each one has exactly one
            correct answer, computed from the formulas and the dependency map.
          </DialogDescription>
        </DialogHeader>
        <div className="scroll-thin max-h-[60vh] space-y-5 overflow-y-auto px-5 py-4">
          {CATEGORIES.map((category) => (
            <section key={category}>
              <div className="eyebrow mb-2">{category}</div>
              <div className="divide-y divide-hairline rounded-lg border border-hairline">
                {Object.values(RULES)
                  .filter((r) => r.category === category)
                  .map((rule) => (
                    <div key={rule.id} className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-ink">{rule.label}</span>
                        <Tag>{rule.id}</Tag>
                      </div>
                      <SeverityPill severity={rule.severity} />
                      <p className="col-span-2 text-[13px] text-ink-secondary">{rule.summary}</p>
                    </div>
                  ))}
              </div>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
