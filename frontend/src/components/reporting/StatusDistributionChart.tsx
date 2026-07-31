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

import { STATUS_CHART_FILL } from "@/components/reporting/constants"
import { cn } from "@/lib/utils"
import { STATUS_LABELS, type TicketStatus } from "@/lib/tickets"

const STATUS_ORDER = Object.keys(STATUS_LABELS) as TicketStatus[]

const ROW_HEIGHT = 28

const TICK_COUNT = 5
// tickCount conta os rotulos; entre eles ha um intervalo a menos.
const TICK_INTERVALS = TICK_COUNT - 1

type Row = { status: TicketStatus; label: string; count: number }

// Teto arredondado do eixo X (Componentes.md: "0 -> teto arredondado acima do
// maximo"): sem isso ("dataMax" puro) a barra maior encosta na borda direita.
// O teto e sempre TICK_INTERVALS vezes um passo redondo, para que os cinco
// rotulos do eixo caiam em multiplos exatos desse passo (0/55/110/165/220 em
// vez de numeros quebrados). O passo escolhido e o menor que cobre o maximo,
// entao o teto fica logo acima dele (214 -> 220, como no mockup) em vez de
// saltar para a proxima potencia de 10 e deixar a maior barra na metade do
// card. Sem dados (tudo zero) cai no teto minimo, evitando um dominio [0, 0].
function axisCeiling(max: number): number {
  if (max <= 0) return TICK_INTERVALS
  const rough = max / TICK_INTERVALS
  // Grade de passos que o Recharts aceita sem reescrever: unidades ate 9, de 5
  // em 5 nas dezenas, de 50 em 50 nas centenas, e assim por diante. Um passo
  // fora dessa grade e substituido por outro e os rotulos deixam de dividir o
  // teto em partes iguais.
  const digits = Math.floor(Math.log10(rough)) + 1
  const grid = digits <= 1 ? 1 : 5 * 10 ** (digits - 2)
  let step = Math.ceil(rough / grid) * grid
  // Teto estritamente acima do maximo: no empate a maior barra encostaria na
  // borda direita do grafico.
  if (step * TICK_INTERVALS <= max) step += grid
  return step * TICK_INTERVALS
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
          tickCount={TICK_COUNT}
          // o eixo conta tickets: rotulo fracionado nao existe neste dominio
          allowDecimals={false}
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
