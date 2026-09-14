/**
 * Book Type
 *
 * Jenis buku sebuah proyek, sepadan dengan app/core/book_type.py di backend.
 *
 * Jenis buku menentukan format kanonik isi bab. Fiksi menyimpan prosa polos berbasis baris,
 * sedangkan non-fiksi menyimpan Markdown karena tabel, daftar bernomor, dan tingkatan judul
 * memikul makna yang tidak dapat diwakili prosa datar.
 */

export const BOOK_TYPES = ["fiction", "non_fiction"] as const;

export type BookType = (typeof BOOK_TYPES)[number];

/**
 * Proyek yang dibuat sebelum jenis buku ada seluruhnya berupa novel, jadi fiksi menjadi bawaan.
 */
export const DEFAULT_BOOK_TYPE: BookType = "fiction";

/**
 * Menyeragamkan jenis buku dari respons backend.
 *
 * Proyek lama dapat mengembalikan medan ini dalam keadaan kosong, sehingga nilai tak dikenal
 * diperlakukan sebagai bawaan alih-alih merusak tampilan daftar proyek.
 */
export function normalizeBookType(raw: unknown): BookType {
  return BOOK_TYPES.includes(raw as BookType) ? (raw as BookType) : DEFAULT_BOOK_TYPE;
}

/**
 * Menyatakan apakah isi bab pada jenis buku ini disimpan sebagai Markdown.
 */
export function usesMarkdownContent(bookType: BookType): boolean {
  return bookType === "non_fiction";
}
