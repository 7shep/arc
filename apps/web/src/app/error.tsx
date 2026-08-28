"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main className="grid min-h-[100dvh] place-items-center p-6"><div className="max-w-md border-l-2 border-red-600 bg-white p-6"><h1 className="text-xl font-semibold">Arc hit an unexpected error.</h1><p className="mt-2 text-sm text-[var(--muted)]">Check that the API and database are running, then try again.</p><button onClick={reset} className="focus-ring mt-5 h-10 bg-[var(--ink)] px-4 text-sm font-medium text-white">Try again</button></div></main>;
}

