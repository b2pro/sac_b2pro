import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { cn } from "@/lib/utils"
import { STATUS_LABELS, type TicketStatus } from "@/lib/tickets"

const STATUS_ORDER = Object.keys(STATUS_LABELS) as TicketStatus[]

const ROW_HEIGHT = 28

// Mesmas familias semanticas de STATUS_ACCENTS (components/tickets/badges.tsx),
// via CSS vars do Tailwind para nao hardcodar hex.
export const STATUS_CHART_FILL: Record<TicketStatus, string> = {
  aberto: "var(--color-sky-600)",
  aguardando_cliente: "var(--color-amber-500)",
  aguardando_analise: "var(--color-violet-500)",
  aprovado: "var(--color-emerald-600)",
  aguardando_envio_reverso: "var(--color-indigo-500)",
  produto_recebido: "var(--color-teal-600)",
  finalizado: "var(--color-emerald-700)",
  declinado: "var(--color-rose-600)",
  cancelado: "var(--color-zinc-400)",
}

type Row = { status: TicketStatus; label: string; count: number }

// Teto arredondado do eixo X (Componentes.md: "0 -> teto arredondado acima do
// maximo"): sem isso ("dataMax" puro) a barra maior encosta na borda direita.
// Arredonda para o primeiro "numero redondo" (1/2/5 x uma potencia de 10)
// estritamente acima do maximo, na magnitude adequada aos dados; todos os
// valores zerados caem no teto minimo (1) em vez de um dominio degenerado [0,0].
function axisCeiling(max: number): number {
  if (max <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(max))
  const normalized = max / magnitude
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10
  const ceiling = step * magnitude
  return ceiling > max ? ceiling : ceiling * 2
}

export function StatusDistributionChart({ counts }: { counts: Record<TicketStatus, number> }) {
  const data: Row[] = STATUS_ORDER.map((status) => ({
    status,
    label: STATUS_LABELS[status],
    count: counts[status] ?? 0,
  }))
  const maxCount = data.reduce((acc, row) => Math.max(acc, row.count), 0)

  return (
    <ResponsiveContainer width="100%" height={data.length * ROW_HEIGHT + 24}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 36, bottom: 0, left: 0 }}>
        <CartesianGrid horizontal={false} stroke="var(--border)" />
        <XAxis
          type="number"
          domain={[0, axisCeiling(maxCount)]}
          tickCount={5}
          axisLine={false}
          tickLine={false}
          tick={{ fontSize: 10, fontFamily: "var(--font-mono)", fill: "var(--muted-foreground)" }}
        />
        <YAxis
          type="category"
          dataKey="label"
          width={172}
          axisLine={false}
          tickLine={false}
          // interval=0 forca a exibicao das 9 categorias: sem isso o Recharts
          // estima o tamanho do tick customizado (abaixo) por uma heuristica
          // generica e pula categorias alternadas, achando que colidiriam.
          interval={0}
          // Tick customizado (em vez do objeto de estilo) para evitar o
          // quebra-linha automatico do Recharts em rotulos longos: o mockup
          // pede uma linha so, truncada se necessario (nowrap + ellipsis).
          tick={({ x, y, payload }) => (
            <text
              x={x}
              y={y}
              dy={4}
              textAnchor="end"
              className="fill-foreground text-[12.5px]"
            >
              {payload.value}
            </text>
          )}
        />
        <Tooltip
          cursor={false}
          content={({ active, payload }) => {
            if (!active || !payload || payload.length === 0) return null
            const row = payload[0]?.payload as Row
            return (
              <div className="rounded-md border border-border bg-card px-2 py-1 text-xs text-foreground">
                {row.label}: {row.count}
              </div>
            )
          }}
        />
        <Bar
          dataKey="count"
          barSize={16}
          radius={3}
          background={{ fill: "var(--muted)", radius: 3 }}
          isAnimationActive={false}
          // Sem isto o Recharts nao gera geometria (nem label) para valor 0:
          // 1px garante que o LabelList consiga posicionar a contagem "0";
          // a Cell de cada status com count=0 usa a cor do trilho (abaixo)
          // para que essa lasca de 1px fique visualmente indistinguivel do
          // trilho — a barra continua "ausente" como o mockup pede.
          minPointSize={1}
        >
          {data.map((row) => (
            <Cell
              key={row.status}
              fill={row.count === 0 ? "var(--muted)" : STATUS_CHART_FILL[row.status]}
            />
          ))}
          <LabelList
            dataKey="count"
            content={({ x, y, width, height, value }) => {
              const count = Number(value ?? 0)
              return (
                <text
                  x={Number(x) + Number(width) + 6}
                  y={Number(y) + Number(height) / 2}
                  dy={4}
                  textAnchor="start"
                  className={cn(
                    "font-mono text-[12.5px]",
                    count === 0 ? "fill-muted-foreground" : "fill-foreground",
                  )}
                >
                  {count}
                </text>
              )
            }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
