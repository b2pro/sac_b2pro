export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-md border border-dashed border-border px-6 py-14 text-center">
      <p className="text-sm font-semibold text-accent-foreground">{title}</p>
      <p className="mt-1.5 text-[13px] text-muted-foreground">{description}</p>
    </div>
  )
}
