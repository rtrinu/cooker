import Reveal from './Reveal'
import bettyImage from '../assets/archive/plates/betty.jpg'
import campImage from '../assets/archive/plates/camp.jpg'
import cookeryImage from '../assets/archive/plates/cookery.jpg'
import hearthImage from '../assets/archive/plates/hearth.jpg'

const plates = [
  {
    src: campImage,
    alt: 'A camp kitchen with a cook tending a fire, 1861.',
    caption: 'Cooking in Camp, 1861',
    width: 900,
    height: 675,
  },
  {
    src: cookeryImage,
    alt: 'A scanned page from an American cookery book, 1915.',
    caption: 'American Cookery, 1915',
    width: 900,
    height: 643,
  },
  {
    src: hearthImage,
    alt: 'A wide hearth in the original kitchen of a farmhouse.',
    caption: 'Farmhouse kitchen, HABS',
    width: 900,
    height: 717,
  },
  {
    src: bettyImage,
    alt: 'A brown betty apple pudding in a baking dish.',
    caption: 'Brown Betty, KaMan',
    width: 900,
    height: 506,
  },
]

export default function ArchivePlates() {
  return (
    <section
      aria-labelledby="archive-plates-title"
      className="mt-20"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="archive-plates-title" className="font-display text-3xl tracking-tight">
          Plates from the archive
        </h2>
        <p className="text-base text-muted">Pages, rooms and puddings behind the catalogue.</p>
      </div>
      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        {plates.map((plate, index) => (
          <Reveal key={plate.caption} delay={index * 60}>
            <figure className="overflow-hidden bg-surface">
              <img
                src={plate.src}
                alt={plate.alt}
                width={plate.width}
                height={plate.height}
                loading="lazy"
                className="image-drift aspect-[4/3] w-full object-cover"
              />
              <figcaption className="px-3 py-2 text-sm text-ink/80">{plate.caption}</figcaption>
            </figure>
          </Reveal>
        ))}
      </div>
    </section>
  )
}
