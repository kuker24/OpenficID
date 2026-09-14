/**
 * Project Types
 *
 * Definisi tipe TypeScript terkait proyek, sepadan dengan Schema backend.
 */

import type { BookType } from "./book-type.types";

/**
 * Entitas proyek
 */
export interface Project {
  id: string;
  title: string;
  description: string | null;
  bookType: BookType;
  /** Jenis buku tidak dapat diubah lagi karena proyek sudah memiliki bab */
  bookTypeLocked: boolean;
  wordCount: number;
  chapterCount: number;
  coverUrl: string | null;
  createdAt: string;
  updatedAt: string;
}

/**
 * Permintaan pembuatan proyek
 */
export interface ProjectCreate {
  title: string;
  description?: string | null;
  bookType?: BookType;
  cover?: File | null;
}

/**
 * Permintaan pembaruan proyek
 */
export interface ProjectUpdate {
  title?: string | null;
  description?: string | null;
  bookType?: BookType | null;
  cover?: File | null;
}

/**
 * Respons daftar proyek
 */
export interface ProjectListResponse {
  items: Project[];
  total: number;
  page: number;
  pageSize: number;
}

/**
 * Parameter kueri daftar proyek
 */
export interface ProjectListParams {
  page?: number;
  pageSize?: number;
  search?: string;
  sortBy?: "updated_at" | "created_at" | "title";
  sortOrder?: "asc" | "desc";
}
