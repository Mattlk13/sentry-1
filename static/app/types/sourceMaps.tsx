export type DebugIdBundleAssociation = {
  dist: string[] | string | null;
  release: string;
  exists?: boolean;
};

export type DebugIdBundle = {
  associations: DebugIdBundleAssociation[];
  bundleId: string;
  date: string;
  dateModified: string;
  fileCount: number;
};

export type DebugIdBundleArtifact = {
  associations: DebugIdBundleAssociation[];
  bundleId: string;
  date: string;
  dateModified: string;
  fileCount: number;
  files: Array<{
    debugId: string;
    filePath: string;
    fileSize: number;
    fileType: number;
    id: string;
    sourcemap: string | null;
  }>;
};
