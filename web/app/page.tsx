import { Suspense } from "react";

import { Workspace } from "@/components/workspace";

// The workspace reads the URL for the selected file, view and cell, and a
// static export needs that behind a Suspense boundary.
export default function Page() {
  return (
    <Suspense fallback={null}>
      <Workspace />
    </Suspense>
  );
}
