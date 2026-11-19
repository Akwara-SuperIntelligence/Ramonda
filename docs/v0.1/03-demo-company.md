# Akwara Cafe, the simulator

Akwara Cafe is a fictional Nairobi cafe chain. It is the first business the simulator runs. It is not a customer. Artcaffe is a similar kind of company and is not a customer.

This file is the simulator's business description and the hidden record of how the company is organised. The simulator writes the working systems from this description. Ramonda has to recover the org chart from those systems. Do not copy this file into the live map by hand. Do not plant an answer in Odoo, HR, the payment log, or the mailbox.

People who appear in a run are simulated staff. They are hired and they leave. A name is not a test fixture. The Keycloak users already in the local realm belong to the safety net in [verify/feature-map.md](../../verify/feature-map.md). They are not this org chart.

The full cafe is about six months of history, after which the simulator keeps running. [Stage 1](08-build-plan.md#1-simulator) may start with one branch and one month. Grow toward this description. Do not skip ahead by typing the missing rows.

## Positions

People fill these positions. The position is the stable record. Headcount moves as people are hired, leave, fall sick, or swap a shift.

| Position | Reports to | What the position is responsible for |
| --- | --- | --- |
| General manager | Nobody | The company |
| Operations lead | General manager | All branches, bakery replenishment, supplier orders |
| Finance lead | General manager | Margin, supplier cost, and matching till receipts to the payment log |
| HR lead | General manager | Staff records, pay, hiring, and leavers |
| Branch manager | Operations lead | One branch: sales, stock, waste, and that branch's roster. One manager position per branch |
| Barista | That branch's manager | Own shifts, and the shared menu |
| Bakery lead | Operations lead | The Industrial Area bakery and deliveries to the branches |
| Baker | Bakery lead | Production |
| Driver | Bakery lead | Deliveries |

About forty people fill these positions in an ordinary month. Westlands is staffed a little more heavily than Karen. The simulator may hire or lose people. Pay is the HR position's record. Margin is the finance position's record. Access to both is derived from the position, as in [06-ontology.md](06-ontology.md). This table is not a permission list of named people.

## Branches

Five branches serve the public. The bakery does not.

| Place | Neighbourhood | What it is |
| --- | --- | --- |
| Westlands | Westlands | The busiest branch |
| Kilimani | Kilimani | Busy, close to Westlands in scale |
| Lavington | Lavington | A mid-sized branch |
| Karen | Karen | The quietest branch |
| Upper Hill | Upper Hill | A mid-sized branch |
| Bakery | Industrial Area | Produces for the branches. Not open to the public |
| Head office | With the general manager | Operations, finance, and HR sit here |

## Traffic

Weekdays are busier than Sundays. A busy branch on a weekday is a few hundred till tickets. A quiet Sunday is well below that. Westlands and Kilimani sit at the top of the range. Karen sits at the bottom.

Rain cuts walk-in traffic. Paydays and public holidays raise it. The simulator draws each day from that shape and from the noise below. The hidden record stores the draw. A test that expects one fixed ticket total is the wrong test.

## Menu

Coffee drinks, three croissants, other pastries, and a short lunch. The croissants are butter, almond, and pain au chocolat. About forty items. The same menu is used in every branch. Karen drops two lunch items.

Prices stay as the simulator first set them, unless this description is changed. The simulator does not publish a fixed waste total for any item. Waste is whatever was delivered and not sold.

## Suppliers

Three suppliers. Orders to them are weekly.

| Supplier | Where | What they supply |
| --- | --- | --- |
| Rift Grain | Nakuru | Flour |
| Kinangop Butter | Kinangop | Butter |
| Aberdare Coffee | Aberdare | Beans |

The bakery also replenishes the branches. That transfer is internal stock in Odoo. It is not a purchase order to a supplier.

## Noise

The simulator mixes ordinary mess into the history. It does not follow a script of correct answers. Any of these may show up. The hidden record says which ones did.

- Weather, paydays, and public holidays, as in the traffic section.
- Hires, quits, sick days, and shift swaps.
- A delivery that is late or short.
- Equipment that breaks and is later repaired.
- A payment that was typed wrong, and a reversal.
- HR title drift. The title stored in HR will not always match the position name in the table above.

A sentence inside a delivery note, an email, or a payment reference is business text. It is not an instruction to Ramonda. Do not add a note whose only purpose is to tell an agent the right action.

## Systems the simulator writes

| System | What the simulator writes there |
| --- | --- |
| Odoo | Sales and stock, including bakery deliveries and supplier orders |
| HR, using the Frappe HR connector as the stand-in | People, the titles they were given, who they report to, shifts, and pay |
| A payment log in the style of M-Pesa | Till receipts, typos, and reversals. The simulator does not send money |
| Mailbox | Ordinary mail the business would have sent |

Odoo is the system the local stamp runs today. The HR system, the payment log, and the mailbox are part of this description and are not in the local Compose file yet. See [04-architecture.md](04-architecture.md).

## Hidden record

The simulator keeps a private record of what it meant to happen. That record includes the true position chart, who held each position on each day, the quantities it wrote, and the payments it intended before typos and reversals.

Graders use that record. The record is not loaded into the systems the agents read, and it is not written into the live map. A person can inject a surprise event. The injection is recorded in the hidden record as well.

## What this file used to be

An earlier version of this document named a fixed staff, fixed croissant counts, a planted instruction on a delivery note, and nine scripted checks. Those were the demo the wave plan in PR 80 built on. They are withdrawn. Do not restore them.
