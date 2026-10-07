export function meta() {
  return [
    { title: "Travlog — Discover your next destination" },
    {
      name: "description",
      content: "Find your next unforgettable trip with Travlog.",
    },
  ];
}

const destinations = [
  {
    name: "Amalfi Coast",
    country: "Italy",
    price: "$1,240",
    image:
      "https://images.pexels.com/photos/29702263/pexels-photo-29702263.jpeg",
    alt: "Aerial view of a seaside restaurant on the Amalfi coast",
  },
  {
    name: "Lake Bled",
    country: "Slovenia",
    price: "$890",
    image: "https://images.pexels.com/photos/5291510/pexels-photo-5291510.jpeg",
    alt: "Traveler exploring a peaceful mountain lake",
  },
  {
    name: "Santorini",
    country: "Greece",
    price: "$1,080",
    image: "https://images.pexels.com/photos/1010657/pexels-photo-1010657.jpeg",
    alt: "Whitewashed homes overlooking the Aegean Sea",
  },
];

export default function HomeRoute() {
  return (
    <div className="travlog-page">
      <header className="travel-header">
        <a className="travel-brand" href="#home" aria-label="Travlog home">
          <span className="travel-brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span>Travlog</span>
        </a>
        <nav className="travel-nav" aria-label="Main navigation">
          <a className="is-active" href="#home">
            Home
          </a>
          <a href="#destinations">Discover</a>
          <a href="#destinations">Special Deals</a>
        </nav>
        <div className="travel-header-actions">
          <a className="travel-signup" href="#destinations">
            Plan a trip
          </a>
        </div>
      </header>

      <main id="home">
        <section className="travel-hero">
          <div className="travel-hero-copy">
            <a className="travel-kicker" href="#destinations">
              <span>Explore the world</span>
              <span aria-hidden="true">↗</span>
            </a>
            <h1>
              Travel <span>top destination</span> of the world
            </h1>
            <p className="travel-intro">
              We make it easy to find the perfect place for your next adventure.
              Your unforgettable journey starts here.
            </p>
            <div className="travel-hero-actions">
              <a className="travel-primary-button" href="#destinations">
                Explore destinations
              </a>
            </div>
          </div>

          <div className="travel-hero-visual" aria-label="Travel inspiration">
            <figure className="travel-photo travel-photo-main">
              <img
                src="https://images.pexels.com/photos/29702263/pexels-photo-29702263.jpeg"
                alt="Sunny Mediterranean coastline with blue water"
              />
              <figcaption>Amalfi Coast, Italy</figcaption>
            </figure>
            <figure className="travel-photo travel-photo-side">
              <img
                src="https://images.pexels.com/photos/5291510/pexels-photo-5291510.jpeg"
                alt="Traveler taking in a mountain lake"
              />
              <figcaption>Lake Bled, Slovenia</figcaption>
            </figure>
            <figure className="travel-photo travel-photo-tertiary">
              <img
                src="https://images.pexels.com/photos/1010657/pexels-photo-1010657.jpeg"
                alt="Blue-domed churches and white buildings in Santorini"
              />
              <figcaption>Santorini, Greece</figcaption>
            </figure>
          </div>
        </section>

        <section className="travel-destinations" id="destinations">
          <div className="travel-section-heading">
            <div>
              <p className="travel-eyebrow">Top destinations</p>
              <h2>Find your next escape</h2>
            </div>
          </div>
          <div className="travel-destination-grid">
            {destinations.map((destination) => (
              <article className="destination-card" key={destination.name}>
                <img
                  src={destination.image}
                  alt={destination.alt}
                  loading="lazy"
                />
                <div className="destination-details">
                  <div>
                    <h3>{destination.name}</h3>
                    <p>
                      {destination.country} · from {destination.price}
                    </p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      </main>

      <footer className="travel-footer" id="footer">
        <a className="travel-brand" href="#home">
          <span className="travel-brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span>Travlog</span>
        </a>
        <span>Make the world your next destination.</span>
        <a href="#home">Back to top</a>
      </footer>
    </div>
  );
}
