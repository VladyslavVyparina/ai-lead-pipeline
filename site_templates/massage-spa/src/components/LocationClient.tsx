"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { MapPin, Clock, Phone, MessageCircle } from "lucide-react";
import type { Locale } from "@/i18n-config";
import type { Dictionary } from "@/lib/dictionaries";
import { businessInfo } from "@/lib/business";

interface LocationClientProps {
  lang: Locale;
  dict: Dictionary;
}

export function LocationClient({ lang, dict }: LocationClientProps) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  const lead = (dict as {
    lead?: {
      address: string;
      hours: string;
      contact: { phone: string; whatsappUrl: string };
    };
  }).lead;

  const whatsappLink =
    lead?.contact.whatsappUrl ||
    `${businessInfo.contact.whatsapp}?text=${encodeURIComponent(
      businessInfo.contact.whatsappMessage[lang]
    )}`;
  const phone = lead?.contact.phone || businessInfo.contact.phone;
  const phoneDisplay = lead?.contact.phone || businessInfo.contact.phoneDisplay;

  const mapQuery = lead?.address
    ? encodeURIComponent(lead.address)
    : "Rua+de+Santo+Isidro+134,+4000-473+Porto,+Portugal";
  const googleMapsUrl = lead?.address
    ? `https://www.google.com/maps/dir//${mapQuery}`
    : "https://www.google.com/maps/dir//Rua+de+Santo+Isidro+134,+4000-473+Porto,+Portugal";
  const embedMapUrl = lead?.address
    ? `https://www.google.com/maps?q=${mapQuery}&output=embed`
    : "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3003.8!2d-8.6033!3d41.1537!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x0%3A0x0!2sRua+de+Santo+Isidro+134+Bonfim+Porto!5e0!3m2!1sen!2spt!4v1234567890";

  return (
    <div ref={ref}>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.6 }}
        className="text-center mb-12"
      >
        <span className="text-sage font-sans text-sm tracking-widest uppercase mb-4 block">
          {dict.location.title}
        </span>
        <h2 className="font-serif text-3xl md:text-4xl text-foreground">
          {dict.location.heading}
        </h2>
      </motion.div>

      <div className="grid lg:grid-cols-2 gap-8 lg:gap-12">
        <motion.div
          initial={{ opacity: 0, x: -40 }}
          animate={isInView ? { opacity: 1, x: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="paper-texture p-8 md:p-10"
        >
          <div className="space-y-8">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-full bg-sage/20 flex items-center justify-center flex-shrink-0">
                <MapPin className="text-sage" size={22} />
              </div>
              <div>
                <h3 className="font-sans font-medium text-foreground mb-1">
                  {dict.location.address}
                </h3>
                <a
                  href={googleMapsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-sans text-foreground/80 hover:text-foreground transition-colors leading-relaxed inline-block"
                >
                  {lead?.address ? (
                    lead.address
                  ) : (
                    <>
                      {businessInfo.address.streetAddress}
                      <br />
                      {businessInfo.address.postalCode}{" "}
                      {businessInfo.address.addressLocality}, Portugal
                    </>
                  )}
                </a>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-full bg-terracotta/20 flex items-center justify-center flex-shrink-0">
                <Clock className="text-terracotta-dark" size={22} />
              </div>
              <div>
                <h3 className="font-sans font-medium text-foreground mb-1">
                  {dict.location.hours}
                </h3>
                <p className="font-sans text-foreground/80">
                  {lead ? (
                    <span className="block">
                      {lead.hours || dict.location.hoursWeekday}
                    </span>
                  ) : (
                    <>
                      <span className="block">
                        {dict.location.hoursWeekday}:{" "}
                        {dict.location.hoursWeekdayTime}
                      </span>
                      <span className="block mt-1">
                        {dict.location.hoursSunday}:{" "}
                        {dict.location.hoursSundayTime}
                      </span>
                    </>
                  )}
                </p>
              </div>
            </div>

            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-full bg-sage/20 flex items-center justify-center flex-shrink-0">
                <Phone className="text-sage" size={22} />
              </div>
              <div>
                <h3 className="font-sans font-medium text-foreground mb-1">
                  {dict.location.phone}
                </h3>
                <a
                  href={`tel:${phone}`}
                  className="font-sans text-foreground/80 hover:text-foreground transition-colors"
                >
                  {phoneDisplay}
                </a>
              </div>
            </div>

            <motion.a
              href={whatsappLink}
              target="_blank"
              rel="noopener noreferrer"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="btn-primary flex items-center justify-center gap-2 w-full mt-4"
            >
              <MessageCircle size={18} />
              {dict.sticky.book}
            </motion.a>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 40 }}
          animate={isInView ? { opacity: 1, x: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="relative rounded-2xl overflow-hidden shadow-medium min-h-[400px]"
        >
          {isInView && (
            <iframe
              src={embedMapUrl}
              width="100%"
              height="100%"
              style={{ border: 0, minHeight: "400px" }}
              allowFullScreen
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
              title="Kaapora Location Map"
              className="w-full h-full"
            />
          )}
        </motion.div>
      </div>
    </div>
  );
}
