# UI et accessibilité

## Organisation de l’interface

Le shell combine `SidebarProvider`, `AppSidebar`, un en-tête et `Outlet`. La sidebar Shadcn gère sa variante mobile dans une feuille latérale. `NavLink` indique la route active et la navigation reste utilisable au clavier.

Les primitives de `src/components/ui` encapsulent Radix/Shadcn et les styles communs. Les composants métier les composent ; ils ne doivent pas modifier les primitives pour un besoin propre à une seule page.

`components.json` utilise le style `new-york`, TypeScript, les CSS variables, Lucide et les alias `@/components`, `@/components/ui`, `@/lib`, `@/lib/utils` et `@/hooks`. Vite et TypeScript résolvent `@` vers `src`.

Les primitives présentes sont : `Alert`, `Badge`, `Button`, `Card`, `Checkbox`, `Field`, `Input`, `Label`, `Progress`, `Separator`, `Sheet`, `Sidebar`, `Skeleton`, `Switch`, `Table` et `Tooltip`. Sonner est installé comme toaster global dans `AppProviders`. Cette liste décrit l'état courant, pas un catalogue imposé.

Pour ajouter une primitive :

```bash
cd frontend
pnpm dlx shadcn@latest add <composant>
```

Ne conserver que les composants effectivement importés. Vérifier le diff généré, car l’outil peut modifier les styles ou dépendances partagés.

## Styles, thème et `cn`

`src/index.css` charge Tailwind CSS 4 et définit les tokens de couleur/rayon sous forme de variables CSS pour `:root` et `.dark`. Les classes sémantiques comme `bg-background`, `text-muted-foreground` ou `border-border` doivent être préférées aux couleurs codées en dur dans l'UI générale.

`cn` dans `src/lib/utils.ts` combine `clsx` et `tailwind-merge`. Il sert à composer des classes conditionnelles tout en résolvant les conflits Tailwind :

```tsx
<Button className={cn("w-full", compact && "h-8")} />
```

## Formulaires

- Chaque contrôle doit avoir un `id` stable et un `FieldLabel` avec `htmlFor`.
- Utiliser `FieldDescription` pour l’aide, pas un placeholder comme seul libellé.
- Afficher les validations avec `FieldError` et conserver un texte compréhensible sans dépendre de la couleur.
- Désactiver ou annoncer clairement les actions indisponibles pendant un chargement.
- Conserver les contrôles natifs (`input`, `select`) quand ils répondent au besoin.

## États asynchrones

`RouteLoading` couvre le chargement lazy initial. Les boutons de scan et la liste des marchés affichent un état de chargement. Les erreurs scanner sont rendues dans une alerte. Toute nouvelle opération asynchrone doit prévoir au minimum chargement, succès vide et erreur.

La page marché ne rend pas encore son statut WebSocket : c’est un point d’amélioration avant de considérer l’expérience de panne complète.

## Responsive

Le formulaire passe à plusieurs colonnes selon la largeur. Les tables sont placées dans un conteneur à défilement horizontal. Le graphique utilise une hauteur relative avec un minimum et Lightweight Charts en `autoSize`.

Tester au minimum : navigation mobile, zoom à 200 %, tableau étroit, focus visible, ordre de tabulation et libellé accessible des contrôles. Les marqueurs et couleurs du graphique doivent être accompagnés d’un texte ou d’une métrique lorsque l’information est essentielle.

## Checklist d’un composant

- HTML sémantique et nom accessible ;
- utilisable au clavier ;
- focus non masqué ;
- erreurs et chargements annoncés par du texte ;
- contraste suffisant en thème courant ;
- aucun débordement à 320 px ;
- pas de logique métier enfouie dans une primitive UI.
