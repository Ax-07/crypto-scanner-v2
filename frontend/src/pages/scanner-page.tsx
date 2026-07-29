import { ScannerWorkspace } from "@/features/scanner/components/scanner-workspace";

export function ScannerPage() {
  return (
    <div className="flex w-full flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold">Scanner de marché</h1>
        <p className="text-muted-foreground">
          Analysez les paires selon une configuration validée avant chaque lancement.
        </p>
      </div>
      <ScannerWorkspace />
    </div>
  );
}
