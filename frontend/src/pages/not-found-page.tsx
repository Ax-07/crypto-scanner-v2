import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
export function NotFoundPage() {
  return (
    <div className="grid min-h-[50vh] place-content-center gap-4 text-center">
      <p className="text-6xl font-bold">404</p>
      <h1 className="text-2xl font-semibold">Page introuvable</h1>
      <Button asChild>
        <Link to="/scanner">Retour au scanner</Link>
      </Button>
    </div>
  );
}
