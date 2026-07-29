import { isRouteErrorResponse, Link, useRouteError } from "react-router-dom";
import { Button } from "@/components/ui/button";
export function RouteErrorPage() {
  const error = useRouteError();
  if (import.meta.env.DEV) console.error(error);
  const message = isRouteErrorResponse(error)
    ? error.statusText
    : error instanceof Error
      ? error.message
      : "Erreur inattendue";
  return (
    <div className="grid min-h-screen place-content-center gap-4 p-6 text-center">
      <h1 className="text-2xl font-semibold">Impossible d’afficher cette page</h1>
      <p className="text-muted-foreground">{message}</p>
      <Button asChild>
        <Link to="/scanner">Retour au scanner</Link>
      </Button>
    </div>
  );
}
