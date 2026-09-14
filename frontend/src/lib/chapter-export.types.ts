export const CHAPTER_EXPORT_FORMATS = ["txt", "docx", "pdf"] as const;

export type ChapterExportFormat = (typeof CHAPTER_EXPORT_FORMATS)[number];

export interface ChapterExportCreate {
  selectedVolumeIds: string[];
  includedChapterIds: string[];
  excludedChapterIds: string[];
  localDate: string;
  format: ChapterExportFormat;
}

export interface ChapterExport {
  id: string;
  status: string;
  filename: string;
  format: ChapterExportFormat;
  mode: "chapters" | "volumes";
  volumeCount: number;
  chapterCount: number;
  wordCount: number;
  chapterIds: string[];
  current: number;
  total: number;
  stage: string | null;
  chapterTitle: string | null;
  expiresAt: string | null;
  downloadUrl: string | null;
  errorMessage: string | null;
}
