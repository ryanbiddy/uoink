# Screenshot sources

Every saved source visible in the 3.12.0 store screenshots, captured on
2026-10-31. YouTube licenses were read from each video's own license field
(shown in its description as "Creative Commons Attribution license (reuse
allowed)"). The web pages are works of the US federal government.

## YouTube videos

| Title | Channel | URL | License | Shots |
|---|---|---|---|---|
| Lesson 9 - Lecture 3 - The Origin of the Moon - OpenStax | Introduction to Astronomy | https://www.youtube.com/watch?v=V9w3Fhh9BkM | CC BY (YouTube) | 01, 02, 03, 04 |
| Lesson 9 - Lecture 4 - Mercury - OpenStax | Introduction to Astronomy | https://www.youtube.com/watch?v=Gg7QsqdoZbg | CC BY (YouTube) | 01 (YouTube's own suggestion thumbnail, not saved) |
| Phases of the Moon - OER | Center for eLearning, FSCJ | https://www.youtube.com/watch?v=4kDqdNTBJL0 | CC BY (YouTube) | 02, 03, 04 |
| Photosynthesis & Respiration | FuseSchool - Global Education | https://www.youtube.com/watch?v=3XIyweZg6Sw | CC BY (YouTube) | 02, 03 |
| The Moon - Origin, Structure and Exploration | Astronomy with Mr Guerin | https://www.youtube.com/watch?v=noGJmYSxWd0 | CC BY (YouTube) | 02, 04 |
| Travel Deep Inside a Leaf - Annotated Version | California Academy of Sciences | https://www.youtube.com/watch?v=pwymX2LxnQs | CC BY (YouTube) | 02 |

The OpenStax lecture slide shown in 01 and 03 credits its illustration as
"NASA/JPL-Caltech [Public domain], via Wikimedia Commons".

## Web pages

| Title | Publisher | URL | License | Shots |
|---|---|---|---|---|
| Moon Fact Sheet | NASA Space Science Data Coordinated Archive | https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html | Public domain (US federal government work) | 02, 03, 04 |
| What are spring and neap tides? | NOAA National Ocean Service | https://oceanservice.noaa.gov/facts/springtide.html | Public domain (US federal government work) | 04 |
| What Causes Tides | NOAA National Ocean Service | https://oceanservice.noaa.gov/education/tutorial_tides/tides02_cause.html | Public domain (US federal government work) | None visible; it is one of the 8 saved items counted in 02-04 |

Shot 05 shows only the extension's setup page and no saved sources.

## How the library was built

The library was captured into an empty, isolated review profile from Uoink
3.12.0 (`main` at `d5c2b8b`), through the helper's own `/extract` and
`/extract/page` routes. Nothing was added by hand. The two NOAA hosts and the
NASA host were added to the page allowlist, which is the same step a user
takes the first time they save a page from a site. The profile's topic list
was set to two topics, "Moon and tides" and "Photosynthesis", before capture,
through the same `/settings` save that the Settings topics editor uses.
