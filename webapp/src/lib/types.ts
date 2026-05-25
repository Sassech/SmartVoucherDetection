/**
 * Shared API types — inferred from backend schemas/web.py
 */

export interface StatsResponse {
  total_mes: number;
  duplicados_mes: number;
  tasa_error: number;
}

export interface WebComprobanteItem {
  id_comprobante: string;
  imagen_path: string;
  referencia: string | null;
  monto: string | number | null;
  fecha_deposito: string | null;
  banco: string | null;
  estado_actual: "recibido" | "procesando" | "comparando" | "sospechoso" | "en_revision" | "valido" | "duplicado" | "error";
  fecha_registro: string;
  // Campos extendidos del endpoint de detalle
  texto_extraido?: string | null;
  numero_operacion?: string | null;
  campos_extraidos?: Record<string, unknown> | null;
}

export interface WebListResponse {
  items: WebComprobanteItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface DecisionRequest {
  accion: "aceptar" | "rechazar";
  motivo?: string;
}

export interface FilterState {
  status: string[];
  date_from: string;
  date_to: string;
}
