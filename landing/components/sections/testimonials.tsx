import { Star } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

const testimonials = [
  {
    quote:
      "SaaSify helped us launch our product 3x faster than building from scratch. The built-in billing and team management saved us months of development.",
    author: "Sarah Chen",
    title: "CTO at TechFlow",
    rating: 5,
  },
  {
    quote:
      "We switched from a custom solution to SaaSify and immediately saw a 40% reduction in infrastructure costs. The analytics dashboard is incredibly powerful.",
    author: "Michael Park",
    title: "Founder at DataSync",
    rating: 5,
  },
  {
    quote:
      "The enterprise security features gave our clients the confidence they needed. SOC 2 compliance out of the box was a game-changer for us.",
    author: "Emily Rodriguez",
    title: "CEO at SecureScale",
    rating: 5,
  },
  {
    quote:
      "From idea to first paying customer in just 2 weeks. The onboarding experience and documentation are top-notch.",
    author: "David Kim",
    title: "Co-founder at LaunchPad",
    rating: 5,
  },
  {
    quote:
      "The API-first approach made integrating with our existing tools seamless. Our engineering team loves working with SaaSify.",
    author: "Jessica Liu",
    title: "VP Engineering at IntegrateHQ",
    rating: 5,
  },
  {
    quote:
      "Best decision we made was choosing SaaSify. Customer support is incredibly responsive and the platform just works.",
    author: "Alex Thompson",
    title: "Product Lead at CloudNative",
    rating: 5,
  },
];

export function Testimonials() {
  return (
    <section id="testimonials" className="py-20 md:py-32">
      <div className="container">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
            Loved by Teams Worldwide
          </h2>
          <p className="text-lg text-muted-foreground">
            Join thousands of companies building better products with SaaSify.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {testimonials.map((testimonial, index) => (
            <Card key={index} className="bg-background">
              <CardContent className="pt-6">
                <div className="mb-4 flex gap-1">
                  {Array.from({ length: testimonial.rating }).map((_, i) => (
                    <Star
                      key={i}
                      className="h-4 w-4 fill-primary text-primary"
                    />
                  ))}
                </div>
                <blockquote className="mb-4 text-muted-foreground">
                  &ldquo;{testimonial.quote}&rdquo;
                </blockquote>
                <div className="flex items-center gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                    <span className="text-sm font-semibold text-primary">
                      {testimonial.author
                        .split(" ")
                        .map((n) => n[0])
                        .join("")}
                    </span>
                  </div>
                  <div>
                    <div className="font-semibold">{testimonial.author}</div>
                    <div className="text-sm text-muted-foreground">
                      {testimonial.title}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}
