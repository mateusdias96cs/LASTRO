# Favicon: Lastro (modelo 1a)

Arquivos nesta pasta, prontos para o front end:

- `favicon.svg`: vetor, escala perfeita (use como favicon principal)
- `favicon-16.png`: 16×16
- `favicon-32.png`: 32×32
- `favicon-180.png`: 180×180 (apple-touch-icon)
- `favicon-512.png`: 512×512 (PWA / manifest)

## Onde colocar (Next.js, app router)

No projeto `frontend/`, copie para `public/`:

```
frontend/public/favicon.svg
frontend/public/favicon-16.png
frontend/public/favicon-32.png
frontend/public/apple-touch-icon.png   (renomeie favicon-180.png)
frontend/public/icon-512.png            (renomeie favicon-512.png)
```

## Como referenciar

No `frontend/src/app/layout.tsx`, adicione ao export `metadata`:

```ts
export const metadata: Metadata = {
  title: "Lastro: conformidade Docker & Kubernetes",
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
};
```

Cor de fundo do ícone: `#06141B` (azul-petróleo). Traços: `#AEB9C0` (hexágono externo), `#385260` (interno), `#E7ECEE` (L), `#D97B45` (marca de Plimsoll / ferrugem).
