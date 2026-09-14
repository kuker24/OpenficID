/**
 * Chapter Content Format
 *
 * Menyatukan perbedaan penyuntingan isi bab antara proyek fiksi dan non-fiksi.
 *
 * Fiksi menyimpan prosa polos berbasis baris, sehingga editornya bermode teks polos dan isinya
 * dijembatani lewat konversi baris baru ke HTML. Non-fiksi menyimpan Markdown, sehingga editornya
 * memuat ekstensi teks kaya dan isinya diserialkan sebagai Markdown.
 *
 * Kedua jalur dikumpulkan di satu modul supaya komponen editor tidak menebar percabangan jenis buku
 * di setiap titik simpan dan muat, karena satu titik yang terlewat berarti naskah tersimpan dalam
 * format yang salah.
 */

import type { Editor } from "@tiptap/react";

import { createMarkdownEditorExtensions } from "@/components/markdown-editor-config";
import type { EditorShortcutCallbacks } from "@/components/markdown-editor-config";
import { usesMarkdownContent, type BookType } from "@/lib/book-type.types";
import { htmlToNewlines, newlinesToHtml } from "@/lib/html-utils";

import { createEditorExtensions } from "./editor-config";
import { SearchAndReplace } from "./search-and-replace";

export interface ChapterEditorFormatOptions {
  placeholder: string;
  shortcuts: EditorShortcutCallbacks;
  autoIndent: () => boolean;
  autoConvertPunctuation: () => boolean;
  autoPairSymbols: () => boolean;
}

/**
 * Menyatakan apakah editor bab pada jenis buku ini bermode Markdown.
 */
export function isMarkdownChapterFormat(bookType: BookType): boolean {
  return usesMarkdownContent(bookType);
}

/**
 * Membangun ekstensi editor bab yang sesuai jenis bukunya.
 *
 * Mode Markdown tetap menyertakan cari dan ganti, karena panel pencarian editor bab bergantung pada
 * perintah ekstensi itu dan akan mati tanpa kehadirannya.
 */
export function createChapterEditorExtensions(
  bookType: BookType,
  options: ChapterEditorFormatOptions,
) {
  if (!isMarkdownChapterFormat(bookType)) {
    return createEditorExtensions(options);
  }

  return createMarkdownEditorExtensions({
    placeholder: options.placeholder,
    shortcuts: options.shortcuts,
    additionalExtensions: [SearchAndReplace],
  });
}

/**
 * Membaca isi editor dalam bentuk yang disimpan basis data.
 */
export function readChapterEditorContent(bookType: BookType, editor: Editor): string {
  if (!isMarkdownChapterFormat(bookType)) {
    return htmlToNewlines(editor.getHTML());
  }
  return editor.getMarkdown();
}

/**
 * Menyiapkan isi tersimpan untuk dimuat ke editor.
 */
export function toChapterEditorContent(bookType: BookType, content: string): string {
  if (!isMarkdownChapterFormat(bookType)) {
    return content ? newlinesToHtml(content) : "";
  }
  return content;
}

/**
 * Memuat isi tersimpan ke editor tanpa memicu penandaan perubahan.
 */
export function setChapterEditorContent(bookType: BookType, editor: Editor, content: string): void {
  if (!isMarkdownChapterFormat(bookType)) {
    editor.commands.setContent(toChapterEditorContent(bookType, content), { emitUpdate: false });
    return;
  }
  editor.commands.setContent(content, { contentType: "markdown", emitUpdate: false });
}

/**
 * Membandingkan isi editor saat ini dengan isi tersimpan.
 *
 * Perbandingan dilakukan pada bentuk tersimpan, bukan pada bentuk tampilan, karena serialisasi
 * Markdown dapat menormalkan penulisan tanpa mengubah maknanya sehingga pembandingan bentuk tampilan
 * akan menandai perubahan yang tidak pernah dilakukan pengguna.
 */
export function isChapterEditorContentChanged(
  bookType: BookType,
  editor: Editor,
  storedContent: string,
): boolean {
  return readChapterEditorContent(bookType, editor) !== storedContent;
}
