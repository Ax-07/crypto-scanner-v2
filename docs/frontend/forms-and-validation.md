# Formulaire et validation

Le formulaire scanner combine React Hook Form, le resolver Zod et les primitives `Field` de Shadcn. `ScanConfig` est le type métier ; `scanConfigSchema` valide et normalise la valeur avant `startScan`.

## Cycle de vie

1. `ScannerWorkspace` charge la configuration serveur.
2. `ScannerConfigForm` appelle `reset` lorsque cette configuration arrive.
3. Les changements restent dans React Hook Form.
4. La soumission Zod transforme notamment l’exchange en minuscules et la quote en majuscules.
5. Le callback transmet une configuration valide au store.

Une valeur vide pour `max_pairs` devient `null`. Les champs numériques obligatoires peuvent temporairement produire `NaN` pendant l’édition, mais Zod bloque la soumission. Les listes de périodes utilisent `parsePeriodList` : valeurs séparées par des virgules, entiers de 2 à 1000, uniques, puis triés.

Exemple fidèle d'un champ numérique contrôlé :

```tsx
<Controller
  name="rsi_period"
  control={form.control}
  render={({ field, fieldState }) => (
    <Field data-invalid={fieldState.invalid}>
      <FieldLabel htmlFor={field.name}>Période RSI</FieldLabel>
      <Input
        id={field.name}
        type="number"
        value={Number(field.value)}
        aria-invalid={fieldState.invalid}
        onChange={(event) =>
          field.onChange(event.target.value === "" ? Number.NaN : event.target.valueAsNumber)
        }
      />
      <FieldError errors={[fieldState.error ?? {}]} />
    </Field>
  )}
/>
```

Le projet utilise également `FieldGroup` pour la grille, `FieldSet`/`FieldLegend` pour les groupes et `FieldDescription` pour l'aide. Il n'utilise pas `useController` directement.

```ts
parsePeriodList("50, 20") // [20, 50]
parsePeriodList("20, 20") // null
parsePeriodList("abc")    // null
```

## Contraintes croisées

`superRefine` vérifie les règles que les bornes unitaires ne peuvent exprimer :

- période MACD rapide strictement inférieure à la lente ;
- seuil stochastique de survente inférieur au surachat ;
- au moins SMA ou EMA lorsque les moyennes mobiles sont actives ;
- score de tendance au plus égal au nombre de timeframes ;
- au moins un poids positif pour un indicateur actif lorsque la confluence est utilisée.

Le backend Pydantic reste l’autorité du contrat. Lorsqu’une contrainte change côté serveur, mettre à jour le schéma, les types, les valeurs affichées et les tests dans la même modification.

## Erreurs serveur

`ApiError` normalise les réponses FastAPI, notamment les erreurs 422 dont `detail` est une liste de `{ loc, msg, type }`. Le formulaire associe les chemins reconnus au champ React Hook Form correspondant et conserve une erreur de formulaire pour le diagnostic général.

Pour ajouter un champ :

1. modifier le modèle backend et le type `ScanConfig` ;
2. ajouter sa règle Zod et, si nécessaire, sa relation dans `superRefine` ;
3. ajouter le contrôle avec un label relié par `htmlFor`/`id` ;
4. vérifier le mapping des erreurs FastAPI ;
5. couvrir les limites et interactions dans un test du schéma.
