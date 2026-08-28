import Link from "next/link";

export function Brand() {
  return <Link href="/" className="focus-ring inline-flex items-center gap-3 font-semibold tracking-[-0.03em]"><span className="grid size-8 place-items-center bg-[var(--ink)] text-sm text-white">A</span><span className="text-lg">Arc</span></Link>;
}

