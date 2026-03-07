"use client";

import { useState } from "react";
import { Menu, X } from "lucide-react";

function FlowerLogo({ size = 36 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Kvitkova Povnya logo"
    >
      {/* Outer glow circle */}
      <circle cx="32" cy="32" r="30" fill="rgba(212,165,191,0.06)" />
      <circle
        cx="32"
        cy="32"
        r="30"
        stroke="rgba(212,165,191,0.18)"
        strokeWidth="0.75"
      />

      {/* Petals — 8 petals arranged radially */}
      {Array.from({ length: 8 }).map((_, i) => {
        const angle = (i * 45 * Math.PI) / 180;
        const cx = 32 + 13 * Math.cos(angle);
        const cy = 32 + 13 * Math.sin(angle);
        return (
          <ellipse
            key={i}
            cx={cx}
            cy={cy}
            rx="4.5"
            ry="8"
            transform={`rotate(${i * 45}, ${cx}, ${cy})`}
            fill={i % 2 === 0 ? "rgba(212,165,191,0.85)" : "rgba(201,169,110,0.75)"}
          />
        );
      })}

      {/* Inner circle / centre */}
      <circle cx="32" cy="32" r="7" fill="#0a0a12" />
      <circle cx="32" cy="32" r="5.5" fill="#d4a5bf" opacity="0.9" />
      <circle cx="32" cy="32" r="3" fill="#c9a96e" opacity="0.95" />
      <circle cx="32" cy="32" r="1.5" fill="#0a0a12" />

      {/* Stem */}
      <path
        d="M32 44 Q34 52 30 58"
        stroke="rgba(107,176,138,0.7)"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
      />
      {/* Leaf */}
      <path
        d="M32 50 Q38 46 40 50 Q36 54 32 50Z"
        fill="rgba(107,176,138,0.55)"
      />
    </svg>
  );
}

const navLinks = [
  { label: "Оптимізатор", href: "#optimizer" },
  //{ label: "Результати", href: "#results" },
  //{ label: "Карта", href: "#map" },
];

export default function Header() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 w-full glass border-b border-border">
      {/* Decorative top line */}
      <div className="h-px w-full bg-gradient-to-r from-transparent via-rose-soft/40 to-transparent" />

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo + Brand */}
          <a href="#" className="flex items-center gap-3 group">
            <div className="relative transition-transform duration-300 group-hover:scale-105">
              <FlowerLogo size={40} />
            </div>
            <div className="flex flex-col leading-tight">
              <span className="font-serif text-lg font-semibold tracking-wide text-gradient-rose">
                KVITKOVA
              </span>
              <span className="text-[10px] font-light tracking-[0.25em] text-text-secondary uppercase -mt-0.5">
                POVNYA
              </span>
            </div>
          </a>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                className="px-4 py-2 text-sm text-text-secondary hover:text-text-primary
                           rounded-xl hover:bg-white/5 transition-all duration-200"
              >
                {link.label}
              </a>
            ))}
          </nav>

          {/* CTA + Mobile toggle */}
          <div className="flex items-center gap-3">
            <a
              href="#optimizer"
              className="hidden sm:inline-flex items-center gap-2 px-4 py-2 text-sm font-medium
                         rounded-xl bg-rose-soft/10 border border-rose-soft/20 text-rose-soft
                         hover:bg-rose-soft/20 hover:border-rose-soft/40 transition-all duration-200"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M5 12h14M12 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Почати
            </a>

            {/* Mobile menu button */}
            <button
              className="md:hidden p-2 rounded-xl text-text-secondary hover:text-text-primary
                         hover:bg-white/5 transition-all duration-200"
              onClick={() => setMenuOpen(!menuOpen)}
              aria-label="Toggle menu"
            >
              {menuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="md:hidden border-t border-border bg-bg-card/95 backdrop-blur-xl">
          <nav className="flex flex-col px-4 py-3 gap-1">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className="px-4 py-3 text-sm text-text-secondary hover:text-text-primary
                           rounded-xl hover:bg-white/5 transition-all duration-200"
              >
                {link.label}
              </a>
            ))}
          </nav>
        </div>
      )}
    </header>
  );
}
