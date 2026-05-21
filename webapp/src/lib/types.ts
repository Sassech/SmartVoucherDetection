/**
 * Shared API types — inferred from backend schemas/web.py
 */

export interface StatsResponse {
  total_comprobantes: number;
  pendientes: number;
  procesados_hoy: number;
  duplicados_detectados: number;
}

export interface WebComprobanteItem {
  id_comprobante: string;
  folio: string;
  monto: number | null;
  banco: string | null;
  referencia: string | null;
  fecha_deposito: string | null;
  estado: "pendiente" | "procesado" | "duplicado" | "error" | "sospechoso" | "en_revision";
  imagen_path: string | null;
  texto_extraido: string | null;
}

export interface WebListResponse {
  items: WebComprobanteItem[];
  total: number;
  page: number;
  has_more: boolean;
}

export interface DecisionRequest {
  decision: "valido" | "duplicado";
  notas?: string;
}

export interface FilterState {
  status: string[];
  date_from: string;
  date_to: string;
}
