import { useMutation, useQuery } from "@tanstack/react-query"
import { Pencil, Plus, Trash2 } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { AutocompleteField } from "@/components/tickets/AutocompleteField"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ApiError } from "@/lib/api"
import { listCatalog, listProducts } from "@/lib/cadastros"
import {
  addTicketItem,
  canEditTicket,
  removeTicketItem,
  updateTicketItem,
  type TicketDetail,
  type TicketItemView,
} from "@/lib/tickets"

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "erro inesperado"
}

type ItemDialog = "adicionar" | "editar" | "remover" | null

export function ItemsCard({
  detail,
  role,
  isOwner,
  onChanged,
}: {
  detail: TicketDetail
  role: string | null
  isOwner: boolean
  onChanged: () => void
}) {
  const { ticket, items } = detail
  const canEdit = canEditTicket(role, isOwner, ticket.status)

  const [dialog, setDialog] = useState<ItemDialog>(null)
  const [target, setTarget] = useState<TicketItemView | null>(null)
  const [productId, setProductId] = useState("")
  const [productQuery, setProductQuery] = useState("")
  const [defectTypeId, setDefectTypeId] = useState("")
  const [quantity, setQuantity] = useState(1)

  const { data: defectTypes } = useQuery({
    queryKey: ["defeitos"],
    queryFn: () => listCatalog("defeitos"),
    enabled: dialog === "adicionar" || dialog === "editar",
  })

  function openAdd() {
    setTarget(null)
    setProductId("")
    setProductQuery("")
    setDefectTypeId("")
    setQuantity(1)
    setDialog("adicionar")
  }

  function openEdit(item: TicketItemView) {
    setTarget(item)
    setProductId(item.product_id)
    setProductQuery(item.product_name)
    setDefectTypeId(item.defect_type_id)
    setQuantity(item.quantity)
    setDialog("editar")
  }

  function openRemove(item: TicketItemView) {
    setTarget(item)
    setDialog("remover")
  }

  function closeDialog() {
    setDialog(null)
    setTarget(null)
  }

  const onSuccess = (message: string) => () => {
    toast.success(message)
    closeDialog()
    onChanged()
  }
  const onError = (error: unknown) => toast.error(errorMessage(error))

  const addMutation = useMutation({
    mutationFn: () =>
      addTicketItem(ticket.id, {
        product_id: productId,
        defect_type_id: defectTypeId,
        quantity,
      }),
    onSuccess: onSuccess("Item adicionado"),
    onError,
  })

  const updateMutation = useMutation({
    mutationFn: () =>
      updateTicketItem(ticket.id, target!.id, {
        product_id: productId,
        defect_type_id: defectTypeId,
        quantity,
      }),
    onSuccess: onSuccess("Item atualizado"),
    onError,
  })

  const removeMutation = useMutation({
    mutationFn: () => removeTicketItem(ticket.id, target!.id),
    onSuccess: onSuccess("Item removido"),
    onError,
  })

  function onSubmitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!productId) {
      toast.error("Selecione o produto")
      return
    }
    if (!defectTypeId) {
      toast.error("Selecione o defeito")
      return
    }
    if (dialog === "editar") {
      updateMutation.mutate()
    } else {
      addMutation.mutate()
    }
  }

  const saving = addMutation.isPending || updateMutation.isPending

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle>Itens</CardTitle>
        {canEdit && (
          <Button type="button" variant="outline" size="sm" onClick={openAdd}>
            <Plus size={16} strokeWidth={1.5} />
            Adicionar item
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum item registrado.</p>
        ) : (
          <div className="rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Produto</TableHead>
                  <TableHead>Defeito</TableHead>
                  <TableHead className="text-right">Quantidade</TableHead>
                  {canEdit && <TableHead className="text-right">Acoes</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{item.product_name}</TableCell>
                    <TableCell>{item.defect_type_name}</TableCell>
                    <TableCell className="text-right">{item.quantity}</TableCell>
                    {canEdit && (
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => openEdit(item)}
                            aria-label={`Editar item ${item.product_name}`}
                          >
                            <Pencil size={16} strokeWidth={1.5} />
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => openRemove(item)}
                            aria-label={`Remover item ${item.product_name}`}
                          >
                            <Trash2 size={16} strokeWidth={1.5} />
                          </Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>

      <Dialog
        open={dialog === "adicionar" || dialog === "editar"}
        onOpenChange={(open) => !open && closeDialog()}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{dialog === "editar" ? "Editar item" : "Adicionar item"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={onSubmitForm} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="item-produto">Produto</Label>
              <AutocompleteField
                id="item-produto"
                placeholder="Buscar produto por nome ou SKU"
                value={productQuery}
                onValueChange={(value) => {
                  setProductQuery(value)
                  setProductId("")
                }}
                onSelect={(option) => {
                  setProductId(option.id)
                  setProductQuery(option.label)
                }}
                queryKey="item-card-produto"
                fetchOptions={async (search) => {
                  const page = await listProducts({ search, perPage: 10 })
                  return page.items.map((product) => ({
                    id: product.id,
                    label: product.name,
                    sublabel: product.sku,
                  }))
                }}
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="item-defeito">Defeito</Label>
              <Select value={defectTypeId || undefined} onValueChange={setDefectTypeId}>
                <SelectTrigger id="item-defeito" className="w-full">
                  <SelectValue placeholder="Selecione o defeito" />
                </SelectTrigger>
                <SelectContent>
                  {(defectTypes ?? []).map((defect) => (
                    <SelectItem key={defect.id} value={defect.id}>
                      {defect.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="item-quantidade">Quantidade</Label>
              <Input
                id="item-quantidade"
                type="number"
                min={1}
                value={quantity}
                onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))}
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDialog}>
                Cancelar
              </Button>
              <Button type="submit" disabled={saving}>
                {dialog === "editar" ? "Salvar" : "Adicionar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={dialog === "remover"} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remover item</DialogTitle>
            <DialogDescription>
              {target
                ? `Remover "${target.product_name}" deste ticket? Esta acao nao pode ser desfeita.`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeDialog}>
              Cancelar
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={removeMutation.isPending}
              onClick={() => removeMutation.mutate()}
            >
              Remover
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
