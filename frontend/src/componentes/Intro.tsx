"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Abertura: o traço do logo se desenha e voa até a marca do menu.
 *
 * Roda uma vez por carga e some. Duas escolhas que evitam irritação:
 * qualquer clique ou tecla encerra na hora, e `prefers-reduced-motion` pula
 * tudo. Animação de entrada que não se pode interromper vira pedágio.
 */
export function Intro({ aoTerminar }: { aoTerminar: () => void }) {
  const [saindo, setSaindo] = useState(false);
  const voador = useRef<HTMLDivElement>(null);
  const terminou = useRef(false);

  useEffect(() => {
    const encerrar = () => {
      if (terminou.current) return;
      terminou.current = true;
      setSaindo(true);
      setTimeout(aoTerminar, 700);
    };

    const reduzido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduzido) {
      aoTerminar();
      return;
    }

    // Voa até a marca do menu: mede as duas caixas e interpola, em vez de
    // fixar coordenadas: o menu muda de posição com a largura da tela.
    const voo = setTimeout(() => {
      const alvo = document.getElementById("ls-navmark");
      const origem = document.getElementById("ls-intro-mark");
      if (!alvo || !origem || !voador.current) return;
      const o = origem.getBoundingClientRect();
      const a = alvo.getBoundingClientRect();
      const escala = a.width / o.width;
      const dx = a.left + a.width / 2 - (o.left + o.width / 2);
      const dy = a.top + a.height / 2 - (o.top + o.height / 2);
      voador.current.style.transition = "transform .95s cubic-bezier(.2,0,0,1), opacity .4s";
      voador.current.style.transform =
        `translate(-50%,-50%) translate(${dx}px,${dy}px) scale(${escala})`;
      voador.current.style.opacity = "0";
    }, 3050);

    const fim = setTimeout(encerrar, 3900);
    window.addEventListener("pointerdown", encerrar);
    window.addEventListener("keydown", encerrar);
    return () => {
      clearTimeout(voo);
      clearTimeout(fim);
      window.removeEventListener("pointerdown", encerrar);
      window.removeEventListener("keydown", encerrar);
    };
  }, [aoTerminar]);

  return (
    <div
      className="fixed inset-0 z-[200]"
      style={{
        background: "var(--fundo)",
        opacity: saindo ? 0 : 1,
        transition: "opacity .7s cubic-bezier(.2,0,0,1)",
        pointerEvents: saindo ? "none" : "auto",
      }}
    >
      <div
        ref={voador}
        className="absolute left-1/2 top-[46%] flex -translate-x-1/2 -translate-y-1/2 flex-col
                   items-center gap-[clamp(18px,2.6vw,26px)]"
      >
        <svg
          id="ls-intro-mark"
          viewBox="0 0 100 100"
          fill="none"
          style={{ width: "min(150px,30vw)", height: "auto" }}
          aria-label="Lastro"
        >
          <path
            className="li-draw"
            id="li-hexO"
            pathLength={1}
            d="M28 10 L72 10 L96 50 L72 90 L28 90 L4 50 Z"
            stroke="#AEB9C0"
            strokeWidth="2"
          />
          <path
            className="li-draw"
            id="li-hexI"
            pathLength={1}
            d="M31.1 15.6 L68.9 15.6 L89.6 50 L68.9 84.4 L31.1 84.4 L10.4 50 Z"
            stroke="#385260"
            strokeWidth="1.2"
          />
          <path
            className="li-draw"
            id="li-l"
            pathLength={1}
            d="M41 30 V64 M41 64 H63"
            stroke="#E7ECEE"
            strokeWidth="3"
            strokeLinecap="square"
          />
          <circle id="li-circ" cx="41" cy="52" r="7" stroke="#D97B45" strokeWidth="2.4" fill="none" />
          <path
            className="li-draw"
            id="li-tick"
            pathLength={1}
            d="M30 52 H34 M48 52 H62"
            stroke="#D97B45"
            strokeWidth="2.4"
            strokeLinecap="square"
          />
        </svg>
        <div
          id="li-word"
          style={{
            fontFamily: "var(--serif)",
            fontWeight: 500,
            fontSize: "clamp(28px,3.6vw,40px)",
            letterSpacing: ".28em",
            paddingLeft: ".28em",
            color: "var(--texto)",
          }}
        >
          LASTRO
        </div>
      </div>
    </div>
  );
}
