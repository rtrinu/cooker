export default function RecipeImage({
  src,
  alt,
  className = 'aspect-[21/9] w-full',
}: {
  src?: string
  alt: string
  className?: string
}) {
  if (!src) {
    return null
  }

  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      className={`bg-ink object-cover ${className}`}
    />
  )
}
