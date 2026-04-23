import Link from 'next/link'

export default function MyHigh5LandingPage() {
  const incomeStreams = [
    {
      title: "Annual Verification Fees",
      desc: "When a member pays the $10 annual verification fee, level 1 earns 10%, while levels 2 to 10 earn 1% each."
    },
    {
      title: "Founding Membership",
      desc: "Founding Members join at $100 for the first 1,000 members and $200 thereafter. Sponsors earn 10% on level 1 and 1% on levels 2 to 10."
    },
    {
      title: "Founding Member Subscription",
      desc: "Annual Founding Member subscriptions also reward sponsors with 10% on level 1 and 1% on levels 2 to 10."
    },
    {
      title: "Private Club Subscriptions",
      desc: "Members can create paid private clubs. Affiliate commissions are paid from the 20% platform markup added by the platform."
    },
    {
      title: "Digital Content Sales",
      desc: "Members can sell digital content through the online shop, while sponsors are rewarded from the 20% platform markup."
    },
    {
      title: "Contest Page Ad Revenue",
      desc: "Participants earn 40%, nominators earn 10%, and sponsors earn up to 10 levels deep from ad revenue generated on contest pages."
    },
    {
      title: "Sponsor Ad Slots",
      desc: "When ad slots are bought on the Our Sponsors page, level 1 earns 10%, while levels 2 to 10 earn 1% each."
    }
  ]

  const contestFlow = [
    "Join for free and nominate contestants or vote without account verification.",
    "Verify your account only if you want to participate with your own content.",
    "Participation contests begin at city level, nomination contests begin at country level.",
    "The first round is for nomination or participation, the next round is for voting.",
    "Top contestants advance from city or country level to regional, continental, and global stages."
  ]

  const statCards = [
    ["City to Global", "Structured contest ladder"],
    ["Free to Join", "Nominate and vote"],
    ["Verified Entries", "Authentic participation"],
    ["10-Level Earnings", "Affiliate-powered growth"]
  ]

  const footerLinks = {
    Platform: ["Home", "Contests", "Clubs", "Sponsors"],
    Company: ["About", "Contact", "FAQ", "Download App"],
    Legal: ["Privacy Policy", "Terms of Service", "Cookie Policy"]
  }

  return (
    <div className="min-h-screen bg-[#030712] text-white">
      <header className="sticky top-0 z-50 border-b border-white/10 bg-[#030712]/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center px-4 py-4 sm:px-6 lg:px-8">
          <Link
            href="/dashboard"
            className="flex shrink-0 items-center gap-3 rounded-xl outline-none transition hover:opacity-90 focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#1D4ED8] text-lg font-extrabold shadow-lg shadow-blue-900/40">
              M5
            </div>
            <div>
              <div className="text-lg font-extrabold tracking-tight">MyHigh5</div>
              <div className="text-xs text-slate-400">Global Contest Platform</div>
            </div>
          </Link>
        </div>
      </header>

      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-[#1D4ED8]/25 via-[#030712] to-[#0F172A]" />
        <div className="absolute -top-24 right-0 h-72 w-72 rounded-full bg-[#2563EB]/20 blur-3xl" />
        <div className="absolute bottom-0 left-0 h-72 w-72 rounded-full bg-cyan-500/10 blur-3xl" />

        <div className="relative mx-auto max-w-7xl px-4 py-14 sm:px-6 sm:py-18 lg:px-8 lg:py-24">
          <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-14">
            <div>
              <div className="mb-4 inline-flex items-center rounded-full border border-blue-400/20 bg-blue-500/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-blue-200 sm:text-sm">
                The one and only 360-degree localized global contest platform
              </div>
              <h1 className="max-w-3xl text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl lg:text-6xl">
                Turn local contests into global recognition and recurring income
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300 sm:text-lg sm:leading-8">
                MyHigh5 is the all-in-one localized global contest platform where members can nominate, participate, vote, and earn through a structured contest ecosystem that progresses from city level to the global stage.
              </p>

              <div className="mt-7 flex flex-col gap-3 sm:flex-row">
                <Link
                  href="/dashboard"
                  className="inline-flex items-center justify-center rounded-2xl bg-[#2563EB] px-6 py-3.5 text-base font-bold shadow-lg shadow-blue-900/40 transition hover:bg-[#1D4ED8]"
                >
                  Get Started Free
                </Link>
              </div>

              <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {statCards.map(([value, label]) => (
                  <div key={value} className="rounded-3xl border border-white/10 bg-white/5 p-4 backdrop-blur">
                    <div className="text-base font-extrabold text-white sm:text-lg">{value}</div>
                    <div className="mt-1 text-xs text-slate-300 sm:text-sm">{label}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="relative">
              <div className="rounded-[28px] border border-white/10 bg-white/5 p-3 shadow-2xl backdrop-blur-xl sm:p-4">
                <div className="rounded-[24px] bg-[#0B1220] p-5 sm:p-6">
                  <div className="mb-6 flex items-start justify-between gap-4">
                    <div>
                      <div className="text-sm text-slate-400">Contest Journey</div>
                      <div className="text-2xl font-bold">From Local Stage to Global Spotlight</div>
                    </div>
                    <div className="rounded-xl bg-[#2563EB] px-3 py-2 text-sm font-semibold">Live Model</div>
                  </div>
                  <div className="space-y-3">
                    {["City", "Country", "Regional", "Continental", "Global"].map((stage, i) => (
                      <div key={stage} className="flex items-center gap-4 rounded-2xl border border-white/10 bg-white/5 p-4">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#2563EB] font-bold shadow-md shadow-blue-900/40">
                          {i + 1}
                        </div>
                        <div className="flex-1">
                          <div className="font-semibold">{stage} Level</div>
                          <div className="text-sm text-slate-400">
                            {i === 0 && "Participants start here"}
                            {i === 1 && "Nominated contestants start here"}
                            {i === 2 && "Top winners move into wider competition"}
                            {i === 3 && "Continental visibility for elite contestants"}
                            {i === 4 && "Global final for the best performers"}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8 lg:py-16">
        <div className="mx-auto max-w-3xl text-center">
          <div className="inline-flex rounded-full border border-cyan-400/20 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-200">
            Open access, protected authenticity
          </div>
          <h2 className="mt-4 text-3xl font-bold sm:text-4xl">Anyone can nominate and vote, real participants are identity-backed</h2>
          <p className="mt-4 text-base text-slate-300 sm:text-lg">
            Members can join for free, nominate contestants, and vote without verification. Only those who want to participate with their own content must verify their identity, helping prevent misuse of someone else&apos;s content.
          </p>
        </div>

        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {[
            ["Free Nomination", "Members can nominate contestants in different categories after joining for free."],
            ["Free Voting", "Members can vote in contests without needing account verification."],
            ["Verified Participation", "Participants verify their identity so the uploaded contest content matches the real owner."]
          ].map(([title, desc]) => (
            <div key={title} className="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-lg backdrop-blur">
              <h3 className="text-xl font-bold">{title}</h3>
              <p className="mt-3 text-slate-300">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-white/[0.03] py-14 sm:py-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid gap-10 lg:grid-cols-2 lg:gap-12">
            <div>
              <div className="inline-flex rounded-full border border-blue-400/20 bg-blue-500/10 px-4 py-2 text-sm text-blue-200">
                How it works
              </div>
              <h2 className="mt-4 text-3xl font-bold sm:text-4xl">A monthly contest cycle designed for retention and repeat engagement</h2>
              <div className="mt-8 space-y-4">
                {contestFlow.map((item, idx) => (
                  <div key={idx} className="flex gap-4 rounded-2xl border border-white/10 bg-[#0B1220]/80 p-4">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#2563EB] text-sm font-bold">
                      {idx + 1}
                    </div>
                    <p className="text-slate-300">{item}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[28px] border border-white/10 bg-gradient-to-br from-[#0F172A] to-[#111827] p-6 sm:p-8">
              <div className="text-sm uppercase tracking-[0.2em] text-slate-400">Voting Logic</div>
              <h3 className="mt-3 text-2xl font-bold">Top 5 ranking system</h3>
              <p className="mt-4 text-slate-300">
                Members vote for the top five contestants in each category. The best performers advance progressively from local stages to the world stage, increasing visibility and competition at every level.
              </p>
              <div className="mt-8 grid grid-cols-5 gap-3">
                {[5, 4, 3, 2, 1].map((points) => (
                  <div key={points} className="rounded-2xl border border-white/10 bg-white/5 p-4 text-center">
                    <div className="text-2xl font-extrabold text-blue-300">{points}</div>
                    <div className="mt-1 text-xs text-slate-400">Points</div>
                  </div>
                ))}
              </div>
              <div className="mt-8 rounded-2xl border border-blue-400/20 bg-blue-500/10 p-4 text-blue-100">
                Winners progress from city or country level to regional, continental, and finally global competition.
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8 lg:py-16">
        <div className="mx-auto max-w-3xl text-center">
          <div className="inline-flex rounded-full border border-blue-400/20 bg-blue-500/10 px-4 py-2 text-sm text-blue-200">
            Monetization engine
          </div>
          <h2 className="mt-4 text-3xl font-bold sm:text-4xl">Seven integrated ways members can earn on MyHigh5</h2>
          <p className="mt-4 text-base text-slate-300 sm:text-lg">
            MyHigh5 is built for more than visibility. It is designed to create recurring income opportunities through fees, memberships, subscriptions, commerce, advertising, and sponsorships.
          </p>
        </div>

        <div className="mt-12 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {incomeStreams.map((item, index) => (
            <div key={item.title} className="group rounded-3xl border border-white/10 bg-white/5 p-6 shadow-lg transition hover:-translate-y-1 hover:bg-white/[0.07]">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#2563EB] text-lg font-bold shadow-lg shadow-blue-900/40">
                {index + 1}
              </div>
              <h3 className="mt-5 text-xl font-bold">{item.title}</h3>
              <p className="mt-3 text-slate-300">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-gradient-to-r from-[#1D4ED8] to-[#2563EB] py-14 sm:py-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid gap-8 lg:grid-cols-2 lg:items-center">
            <div>
              <div className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-100">Limited Founding Opportunity</div>
              <h2 className="mt-4 text-3xl font-extrabold sm:text-4xl">Become a Founding Member before all 10,000 slots are filled</h2>
              <p className="mt-4 max-w-2xl text-base text-blue-50/90 sm:text-lg">
                Founding Members gain monthly revenue participation, annual profit-sharing privileges, and the advantage of receiving randomly allocated referrals from members who join without using someone else&apos;s personal invitation link.
              </p>
            </div>
            <div className="rounded-[28px] bg-slate-950/25 p-6 backdrop-blur sm:p-8">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="rounded-2xl bg-white/10 p-5">
                  <div className="text-sm text-blue-100">Joining Fee</div>
                  <div className="mt-2 text-3xl font-bold">$100</div>
                  <div className="text-sm text-blue-100/80">First 1,000 members</div>
                </div>
                <div className="rounded-2xl bg-white/10 p-5">
                  <div className="text-sm text-blue-100">Thereafter</div>
                  <div className="mt-2 text-3xl font-bold">$200</div>
                  <div className="text-sm text-blue-100/80">Until 10,000 slots are filled</div>
                </div>
                <div className="rounded-2xl bg-white/10 p-5 sm:col-span-2">
                  <div className="text-sm text-blue-100">Core Privileges</div>
                  <div className="mt-2 text-blue-50">
                    Share in 10% of monthly website revenues, share in annual profit allocated for Founding Members, receive random referral allocation, and unlock 10-level affiliate earnings.
                  </div>
                </div>
              </div>
              <Link
                href="/dashboard/wallet?product=mfm"
                className="mt-6 flex w-full items-center justify-center rounded-2xl bg-white px-6 py-4 text-base font-bold text-slate-900 transition hover:scale-[1.01]"
              >
                Claim Founding Member Position
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 py-14 text-center sm:px-6 lg:px-8 lg:py-16">
        <h2 className="text-3xl font-bold sm:text-4xl">Compete, nominate, vote, earn, and grow from your local market to the world</h2>
        <p className="mx-auto mt-4 max-w-3xl text-base text-slate-300 sm:text-lg">
          MyHigh5 combines contest participation, verified identity, recurring engagement, and network-driven monetization into one growth-ready digital platform.
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <button className="rounded-2xl bg-[#2563EB] px-6 py-3 font-semibold transition hover:bg-[#1D4ED8]">
            Join MyHigh5 Free
          </button>
          <button className="rounded-2xl border border-white/15 bg-white/5 px-6 py-3 font-semibold transition hover:bg-white/10">
            Explore Earning Opportunities
          </button>
        </div>
      </section>

      <footer className="border-t border-white/10 bg-[#020617]">
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
          <div className="grid gap-10 md:grid-cols-2 lg:grid-cols-5">
            <div className="lg:col-span-2">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#1D4ED8] text-lg font-extrabold shadow-lg shadow-blue-900/40">
                  M5
                </div>
                <div>
                  <div className="text-lg font-extrabold">MyHigh5</div>
                  <div className="text-sm text-slate-400">Localized global contest platform</div>
                </div>
              </div>
              <p className="mt-4 max-w-md text-slate-400">
                A contest platform where members can nominate, participate, vote, and unlock multiple streams of income through a structured city-to-global contest model and a 10-level affiliate system.
              </p>
            </div>

            {Object.entries(footerLinks).map(([group, links]) => (
              <div key={group}>
                <h3 className="text-sm font-bold uppercase tracking-[0.16em] text-slate-300">{group}</h3>
                <ul className="mt-4 space-y-3">
                  {links.map((link) => (
                    <li key={link}>
                      <a href="#" className="text-slate-400 transition hover:text-white">
                        {link}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="mt-10 flex flex-col gap-4 border-t border-white/10 pt-6 text-sm text-slate-500 sm:flex-row sm:items-center sm:justify-between">
            <div>© 2026 MyHigh5. All rights reserved.</div>
            <div>Mobile-first landing page UI adapted to the current MyHigh5 visual direction.</div>
          </div>
        </div>
      </footer>
    </div>
  )
}
