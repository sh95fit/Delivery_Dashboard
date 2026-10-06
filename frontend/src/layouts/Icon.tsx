const PATHS = {
    dashboard: "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z",
    box: "M3 7l9-4 9 4-9 4-9-4zM3 7v10l9 4 9-4V7M12 11v10",
    clock: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18zM12 7v5l3 2",
    won: "M4 6l3 12 3-9h4l3 9 3-12M3 10h18M3 14h18",
    wallet: "M3 7h18v12H3zM3 7l3-3h12l3 3M16 13h2",
    gift: "M3 9h18v4H3zM5 13v8h14v-8M12 9v12M12 9C10 5 6 5 6 7.5S12 9 12 9s6-.5 6-1.5S14 5 12 9",
    grid: "M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18",
    route: "M6 21a2 2 0 1 0 0-4a2 2 0 1 0 0 4zM18 7a2 2 0 1 0 0-4a2 2 0 1 0 0 4zM8 19h7a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7",
    users: "M9 11a4 4 0 1 0 0-8a4 4 0 1 0 0 8zM2 21v-1a6 6 0 0 1 12 0v1M16 3.5a4 4 0 0 1 0 7M22 21v-1a6 6 0 0 0-4-5.6",
    idcard: "M3 5h18v14H3zM9 12a2 2 0 1 0 0-4a2 2 0 1 0 0 4zM5.5 16.5a3.5 3.5 0 0 1 7 0M15 9h3M15 13h3",
    truck: "M1 5h13v11H1zM14 9h4l3 3v4h-7M5.5 20a2 2 0 1 0 0-4a2 2 0 1 0 0 4zM17.5 20a2 2 0 1 0 0-4a2 2 0 1 0 0 4z",
    tag: "M3 3h8l10 10-8 8L3 11zM7.5 7.5h.01",
    lock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4",
    menu: "M3 6h18M3 12h18M3 18h18",
    left: "M15 18l-6-6 6-6",
    right: "M9 18l6-6-6-6",
  } as const;
  
  export type IconName = keyof typeof PATHS;
  
  export default function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={PATHS[name]} />
      </svg>
    );
  }
  