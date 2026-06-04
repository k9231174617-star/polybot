export const isoOrNull = (value: Date | string | null | undefined): string | null => {
  if (!value) {
    return null;
  }

  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
};

export const isoOrNow = (value: Date | string | null | undefined): string => {
  return isoOrNull(value) ?? new Date().toISOString();
};
