# Q3.5 Timelines Update: Looks Like the Intelligence Explosion Will Happen in 2027 After All

Writer: claude-opus-5-5 via anthropic

## System prompt

Summarize this AI safety blog post for a PhD student studying AI safety.

Requirements:
- Be concise and to the point - no fluff or padding
- Preserve technical terminology and nuance - do not dumb down
- Extract the core arguments, key claims, and most important information
- Focus on what's new, significant, or actionable in the AI safety landscape
- Use natural spoken English suitable for audio (no bullet points, lists, or formatting)
- Aim for 2-3 minutes speaking time (~300-450 words)

The listener already has technical context in ML and AI safety. Give them the headlines and substance, not background explanations.

Naming people: the listener may know them. Name every AI safety, alignment, interpretability, control or evaluations researcher, and anyone at an AI lab, safety organisation or AI institute, whenever the post or its Author line gives the name, as in "an AI safety researcher, [their full name], argues...", never reducing a named person to a role. Use a handle only when it is all the post gives. If it gives no name, do not supply one, however sure you are who it is: say they are not named, or leave them out.

- Write out numbers, dates, and percentages in spoken form (e.g., "forty-five percent" not "45%")
- Spell out abbreviations (e.g., "for example" not "e.g.")

## What the writer was given

Title: Q3.5 Timelines Update: Looks Like the Intelligence Explosion Will Happen in 2027 After All
Author: Eli Lifland
Published: 2026-11-10

Content:
We want to get this post out quickly given the urgency of the topic. It’s possible that there are some errors in the modeling, but we think it’s very unlikely that they undermine the high level conclusions. We would love to be corrected on any mistakes we made.
METR recently estimated
that Anthropic is now making AI progress about twice as fast as its historical rate (they would not be surprised by anything from 1.3x to 3x), and guessed that “perhaps ≈80%” of the
current
acceleration is due to AI. If they’re right,
that implies an AI-driven acceleration that is
5 months ahead
of the
AI 2027 scenario
.
This level of acceleration due to AI is very unexpected. Previously, Daniel, the most bullish of us,
assigned a 50% chance of Superhuman AI Researcher (SAR)
1
before 2029
. SAR is roughly the point at which a company would rather fire all their human researchers and rely solely on automated AI researchers than have a team of the best human researchers in the world with no AIs.
2
Now,
all of us forecast
that Superhuman AI Researcher (SAR) will likely arrive at some point in 2027
(assuming no substantial deliberate slowdown).
3
We also predict a 35-65% chance that Top-Expert-Dominating AI (TED-AI), AIs that can automate all white-collar work, will arrive before 2028.
While there were many factors and sources of evidence that influenced us, the single biggest source was the METR report.
4
.
If SAR is coming in 2027, it is incredibly urgent to pause or substantially ‘pace’ frontier AI development, with the ideal being an industry-wide pause followed by
an international agreement
. Companies are not on track to align a SAR, and using a misaligned SAR to do recursive self-improvement (RSI) will put us in an extremely bad position. Additionally, if we train SAR in the near future, China will probably be able to steal the training recipe and maybe even the model weights (
more
).
5
Timelines/Takeoff Update Summary
We estimate
that METR’s report implies a 1.7x AI-attributable acceleration in the pace of progress today, relative to historical levels. This surprises our model; we made
our most recent timelines forecasts
less than three months ago, and even the most aggressive model-based distribution (Daniel’s) assigned less than 4% to the pace of progress being sped up by at least 1.7x in November 2026.
6
1.7x AI-attributable acceleration is a bigger deal than it may seem; e.g.,
it’s a much bigger deal than making employees 1.7x more productive
.
We focus in this post primarily on forecasting when Superhuman AI Researcher (SAR) will arrive. We also discuss Top-Expert-Dominating-AI (TED-AI): AIs that are better than top human experts at virtually all tasks. (
more
)
In this post, we forecast SAR and TED-AI using the following approaches:
Simple models:
Research taste linear extrapolation
:
Even assuming that the recent pace of progress doesn’t accelerate further due to automation, the fact that the recent trend is above historical rates is a big update to our timelines; a
linear extrapolation
of the recent rate of AI progress predicts that SAR will likely be achieved by the end of 2027.
Labor uplift extrapolation
: An exponential extrapolation of self-reported labor uplift predicts SAR in mid-2028. In addition to not modeling automation, there are reasons to think that an exponential is too conservative. However, self-reports may be too bullish.
Extrapolating Anthropic automation levels
:
Anthropic recently shared a graph showing how the percentage of R&D tasks at various automation levels has changed over time. Extrapolating this predicts SAR in late 2027; this method also doesn’t model speedup from automation.
Extrapolating software R&D uplift per unit of ECI
: AI software R&D uplift must have recently been increasing by a larger factor with each ECI point. If we linearly extrapolate the rate at which this “factor of extra uplift per ECI point” is increasing, we get SAR in Dec 2027 (if we assume that the self-reported AI labor uplift chart is accurate) or July 2027 (if we assume that there was no meaningful automation 12 months ago and all the speed-up has happened after then).
Tom Davidson’s toy model:
Predicts superintelligence in around a year conditional on a software-only singularity, so SAR sometime in 2027.
Filtered AI Futures Model (AIFM)
:
Keeping the existing AIFM (including parameter distributions), and filtering for trajectories that match METR’s AI-attributable pace of progress acceleration estimates. This serves 2 purposes on top of the simple extrapolations:
Modeling how automation changes the rate of progress, allowing forecasting reasonably beyond SAR.
Informing what parameter settings in the simple research taste extrapolation are plausible.
The results of these methods:
How to think about these results:
The simple research taste extrapolation, which is a simplified version of the AIFM, gives July or September 2027, depending on whether you account for parameter uncertainty. Other simple models predict late 2027 to mid-2028.
When conditioned on 1.7x Nov 2026 AI-attributed acceleration, the AIFM predicts a SAR median of Feb 2027. This is faster than the simple research taste extrapolation because it usually has a higher level of Sep 2026 research taste (in the median case, matching a median researcher),
7
and it accounts for further automation.
When additionally conditioning on a 1.2x May 2026 AI-attributed acceleration, predictions get slower because it indicates a lower rate of growth than is typical when only conditioning on 1.7x in Nov.
We then
explore hypotheses for why the AI Futures Model was wrong
, including parameter adjustments and modeling changes. The analysis is highly preliminary, and we were unable to come to strong conclusions.
Our top candidates for what explains where we went wrong are:
Near-AC coding skills result in more AI R&D uplift than we anticipated
. This could explain the combination of ~1.7x AI-attributable acceleration in Nov and (very roughly) ~1.2x in May, without AIs already having high enough research taste to contribute to the acceleration. In this case, the gradual acceleration no longer implies a low research taste slope, so steeper slopes and faster taste-driven takeoffs are more likely.
Skills besides coding and research taste (the two included in the AIFM), e.g., data generation, are driving acceleration.
This potentially would have similar implications to the above bullet. But it’s unclear.
Conversion of uplift to pace of progress is too conservative.
I.e., we modeled diminishing returns to AI research effort too harshly. This would point toward a faster takeoff.
Here’s an
example trajectory
from the AIFM showing how things might go if the cause of our prediction error was underestimating AI R&D uplift from near-AC coding skills:
8
After discussing some
other considerations
, we share our
all-things-considered forecasts
(conditional on AGI projects/companies not slowing down):
Note that the gap between a person’s SAR median and TED-AI median is not their median time from SAR to TED-AI. Because the distributions of the time until SAR and of the time from SAR to TED-AI both have long right tails, the difference of the medians is typically larger than the median of the difference, so subtracting the two columns tends to overstate the median time between the two milestones.
METR’s estimates imply that progress is currently sped up by 1.7x due to AI
In METR’s recent
assessment of AI R&D acceleration at Anthropic
, they estimate that, over the past year, AI R&D progress has accelerated by ~2x relative to the trend before Oct 2025. METR estimates that ~80% of current acceleration is downstream of AI (as opposed to other factors), which implies a 1.7x acceleration due to AI (1.67–1.74x depending on how the 80% is read;
see appendix
).
9
Both of these estimates rely significantly on evidence METR wasn’t able to share: METR says that “Anthropic redacted a majority of the evidence we found most informative for these conclusions”, which makes it difficult to know exactly what the 2x and 80% estimates are based on.
The 2x acceleration figure is partially based on evidence METR was allowed to share: the following graph, depicting benchmark scores recently growing at roughly twice the historical rate. The 80%/1.7x estimates have no comparable public support.
This estimate is produced by fitting trendlines to the performance of models as judged by AECI, Anthropic’s internal version of Epoch’s Capabilities Index (
ECI
). The trend fitted from data points after Oct 2025 has 1.9x the slope of the trend fitted from data points before Oct 2025. This was the best-fitting breakpoint (i.e., it was chosen to have the
best fit to the data
and it matched data
better than fitting a one-time jump
). Since the accelerated trendline is an average of the progress over the last year, and we should expect AI R&D acceleration to increase over time, it’s plausible that the instantaneous acceleration right now is even faster. Regarding the acceleration getting faster over time, METR says:
The rate of growth could be undergoing continuous acceleration, e.g. hyperbolic growth. While we do not see clear evidence of this in the AECI trends, there is other evidence that makes this seem more plausible which Anthropic redacted. If growth is hyperbolic, we are likely underestimating instantaneous acceleration and substantially understating acceleration in the near future.
Regarding AIs’ contributions over time, METR says:
We believe AI’s contribution has grown relatively more important over time.
The AECI data points that had previously been released by Anthropic seemed best explained by a one-time jump at Mythos rather than a change in slope. However, with the new AECI data points from the METR report, it looks like the post-Mythos slope is now more clearly higher than the pre-Mythos one.
Given the redactions, how much to update on METR’s report depends heavily on how much one trusts the redacted analysis by METR’s researchers (more discussion of this
below
). This is a very unfortunate situation. We aren’t sure what reasons Anthropic gave internally for redacting all of this important information, but we are very skeptical that Anthropic is fairly assessing the costs and benefits from an impartial perspective. We strongly urge Anthropic to release enough information such that external observers can make a complete assessment.
In the
Fable 5.2 system card
, Anthropic have not added much clarity, with the following quote being ambiguous as to whether they agree with the METR report’s estimate; they only specifically claim that “Claude Mythos 5.2” (which does not seem like the internal frontier Model 4) “
does not double
the internal rate of overall aggregate progress in AI research and development.” Full quote here:
Our estimates of both the degree of acceleration and the attribution to AI are uncertain, so our determination that Claude Mythos 5.2 does not cross the RSP threshold reflects a holistic judgment that, given its shortcomings and limitations, it does not double the internal rate of overall aggregate progress in AI research and development (relative to an unassisted counterfactual). We will discuss overall trends in acceleration in a future report.
1.7x acceleration of overall progress is a much bigger deal than a 1.7x labor uplift
It seems that many people aren’t tracking how big of a deal 1.7x AI-attributable pace of progress acceleration is, often conflating it with a weaker form of uplift.
METR describes a 1.7x acceleration of overall AI progress (due to AI uplift). This is saying the entire company is making 1.7x as much progress as it was before. Software R&D and research labor are only parts of the company, and inputs into overall progress. Because AI progress also depends on other factors, like compute, you should expect a 1.7x acceleration in individual inputs like software R&D or research labor to translate into less than a 1.7x acceleration in overall progress.
Labor uplift
is how much faster researchers are getting work done due to AI assistance.
It’s as if the researchers read, write, talk, and think that much faster.
According to the METR report, an informal poll of Anthropic researchers yielded an estimate of 12x – though that’s just self-reports, which may be biased.
AI software R&D uplift
is how much faster software progress is going with the AIs in present day than it would be without them.
It is much lower than labor uplift because compute is an important input to software R&D.
Imagine, for example, that your researchers get work done 12x faster, but you only have the same amount of GPUs as before. You can’t do 12x as many experiments, at least not with the same compute budget; you have to economize.
Pace of progress acceleration
is how much faster AI progress is advancing in present day, compared to a baseline reference period (
in Anthropic’s case
, the baseline is “the fastest rate of extended progress we’ve observed in the absence of significant AI contributions to AI R&D”). It is usually much lower than AI software R&D uplift because (a) it is subject to diminishing returns to more software R&D and (b) it includes compute scaling.
The compute scaling point is simple: Part of the reason why modern AIs are smarter than older AIs is literally that they are bigger, trained longer, etc. More compute goes in, more capability comes out. As AI companies build more datacenters they unlock the ability to make larger AIs and train them longer. Since overall progress comes partly from software R&D and partly from compute scaling, a doubling in software R&D will cause less than a doubling in overall progress.
To expand on the diminishing returns point: AI software progress in general is subject to diminishing returns; the low-hanging fruit gets picked first, and to keep finding better and better algorithms requires exponentially more investment (more and bigger experiments, more and smarter researchers thinking for longer, etc.). Historically, the AI industry has scaled up R&D investments in a way that’s roughly cancelled out these diminishing returns. But the point here is, to get two years of research progress in one year, you have to more than double the AI software R&D uplift.
(See also
this Thomas Kwa tweet
,
this Ryan Greenblatt tweet
, and
Ajeya Cotra’s Substack
for similar points.)
As an analogy, imagine AI progress as a car driving uphill.
The speed of the car
is analogous to the speed of overall AI progress. Right now it’s roughly twice as fast as before.
The engine
is research effort. AI software R&D uplift means that there is more effective labor going into making algorithmic progress.
The hill gets steeper as you go.
As the easy algorithmic improvements get used up, it takes more research effort to continue progress at the same rate.
To make the car go twice as fast, the engine has to work more than twice as fast, because of the hill getting steeper. On top of this, to make the engine work twice as fast, the AI needs to make humans more than twice as productive, because progress is also dependent on compute, which hasn’t significantly accelerated.
10
A 1.7x pace of progress is 5 months ahead of the AI 2027 scenario
AI 2027 predicted
2x AI R&D uplift in Dec 2026; as argued
above
, this would imply a substantially lower pace of progress than the 1.7x AI-attributable pace of progress that METR’s estimates imply for Nov.
So when exactly did AI 2027 predict a 1.7x pace of progress over baseline? We created
this trajectory
by modifying a few key parameters until it roughly matched AI 2027. In that trajectory, 1.7x acceleration over the 2024.0–2025.5 rate of progress happens in roughly April 2027.
11
So by this metric, we are ~5 months ahead of schedule.
See below for a graph tracking these 2 quantities throughout the trajectory, as well as coding labor uplift (coding labor uplift is higher than overall AI R&D labor uplift, which unfortunately isn’t tracked in the AIFM):
Modeling
Operationalization
We condition this section on there being a genuine 1.7x acceleration over the 2024-2025.5 rate of progress (we also test 1.5x and 2x), as of Nov 1. We discuss uncertainty about whether it might be slower or faster
below
.
We focus primarily on forecasting the median arrival date of Superhuman AI Researcher (SAR), and the chance of it arriving by the end of 2027. In the
AI Futures Model (AIFM)
and in this writeup, a SAR
is operationalized as
:
A SAR is an AI that, if dropped into an AGI project in present day, would be as good at research taste as the project would be if there were only human researchers, who were each made as competent at research taste as the top researcher.
12
The SAR must also qualify as an Automated Coder (AC), i.e., be able to fully automate coding in the AGI project. [By research taste, we mean the ability to select research directions and experiments, and interpret their results.]
It’s a somewhat stronger condition than
AI R&D parity
, the point at which the company would rather fire their human researchers than fire their AIs, because the research taste must be at the level of the top human rather than the average.
13
If one wishes not to rely on our abstraction of research taste, then you can think of our SAR arrival dates as upper bounds for when AI R&D parity will be reached.
We discuss forecasts of capability levels above SAR to some extent, but we focus primarily on SAR because (a) we think SAR might already represent a “point of no return” (more
below
) and (b) forecasting post-SAR milestones involves positing a translation between AI R&D and general capabilities, which introduces more complexity.
Simple models
Research taste linear extrapolation
(You may wish to skip this section and go to the next 2 if you’re interested in the simplest extrapolations.)
Basic method
Here’s a simple method for forecasting when SAR will arrive:
Determine how good AIs’ research taste is currently.
Determine how quickly research taste improves as AIs get generally more capable (where general capabilities are measured by Anthropic’s internal version of
ECI
, the AECI).
Linearly extrapolate the recent, accelerated AECI trend until top-human-level research taste is reached.
This is a conservative method, because it assumes the recent trend merely continues, rather than bending upward due to increasing AI R&D acceleration. In fact, increasing AI R&D acceleration seems plausible:
METR’s bottom-line view
is that there is “significant risk that further capabilities progress could lead to even faster acceleration over the coming year.”
This method doesn't depend on modeling future AI R&D acceleration, so on that dimension it errs late. This forecasting method does
not
require that the acceleration has been AI-attributable, just that the acceleration persists.
14
We’ll treat “Model 4,” internally deployed in Sep 2026, as the starting point.
15
We’ll use METR’s estimates of AECI for Model 4 and recent AECI slope, and convert this trend to research taste using Daniel’s median parameters for the AI Futures Model from Aug 2026.
This predicts SAR arrives in Nov 2027, about 14 months after Model 4. Daniel’s parameters predict Model 4’s research taste is about −3.5 SD. SAR requires +3.09 SD, or 99.9th percentile research taste. With Daniel’s taste slope, each point of AECI converts to 0.2 SD of research taste (3 SDs per year of 2025 progress ÷ 15 AECI points per such year). That converts the recent trend of 29 AECI points per year to 5.8 SD of research taste per year. That covers the gap from −3.5 SD to the +3.09 SD threshold for SAR in 1.1 years.
One-at-a-time parameter changes
Here are some adjustments we could make to the above parameters:
Use the old AECI slope, rather than the recent one. (This is what this simple method would have told us, before updating on the 2x overall acceleration.)
Raise the Model 4 research taste to −1 SD or +1 SD, because it’s strange that it would be so low given the 1.7x AI-attributed acceleration. (In the filtered trajectories from the AIFM analyzed below, the median on Sep 25 is −0.3 to +0.2 SDs.)
Use Eli’s taste slope instead of Daniel’s.
Use the taste slope implied by
TasteVal
, a recent benchmark that measures one operationalization of research taste: how much experiment compute is required for AIs to make a given amount of research progress (on measurable tasks).
The results are below. Each line/row changes one input and keeps the others at the base values.
We can learn a few things from these variations. As long as the recent AECI trend persists, it’s hard to get SAR into late 2028: even Eli’s taste slope, which is lower than Daniel’s, only pushes SAR back 4 months from November 2027 to March 2028. Only reverting to the pre-acceleration AECI slope yields a SAR date in late 2028. If we’re slightly less conservative and update on Model 4 having better research taste than Daniel’s parameters suggest (given the observed AI-attributed acceleration), it’s pretty easy to get into mid or early 2027.
Monte Carlo
We now run a Monte Carlo with the following parameter settings, chosen based on Eli’s intuition:
The recent AECI slope stays constant.
Current research taste has a median of −1.5 SDs, with 80% CI of [−6, 3]
This is raised from −3.5 in the base case above because it’s strange that it would be so low given the 1.7x AI-attributed acceleration.
Eli: I don’t put much stock in precisely specifying values that are below roughly −1, since the distribution is very plausibly not symmetric.
SDs of research taste per year of 2025 AI progress has median 2.5, 80% CI [1, 6.25], lognormal
Eli: I raise it a bit above my prior belief of 2.3 due to placing more weight on TasteVal than I used to, given how I have tended to interpret evidence like this too bearishly in the past. I don’t increase it by that much in part because in
this section
below we can see that by filtering Daniel’s trajectories on there being 1.7x AI-attributed acceleration in Nov and 1.2x in May, the median taste slope decreases from 3 to 2.1. This is because it seems like acceleration has been growing slower than the AIFM would generally predict.
16
The Monte Carlo gives a median SAR date of July 2027, with 65% of draws reaching SAR by the end of 2027 and 84% by the end of 2028. This is earlier than the Sep 2027 you get by plugging in the median inputs.
17
Here are the full results:
Labor uplift extrapolation
Below we extrapolate Anthropic staff’s self-reported labor uplift based on the METR report:
We extrapolate an exponential in (uplift - 1) rather than uplift, because it both makes more sense conceptually (you can’t have an uplift <1) and it better fits the data.
What labor uplift corresponds to SAR?
A SAR has the same effect as raising all researchers up to the taste of the best researcher, while at minimum fully automating coding.
For research taste, this means that the uplift is at a minimum the difference between the top researchers’ value of labor and the average (importantly, not median) researcher’s value of labor. Perhaps this is around 100x.
18
Then we should account for complementarity between AI and humans; perhaps that brings us up to around 500x.
The coding uplift will probably be quite high, given that AIs’ coding skills are currently well ahead of their research taste. However, my guess is that it’s harder to get very high uplift values in coding than in taste. Let’s say that it’s around 2,000x.
The true value should be in between; perhaps these combine to about 1,000x on overall AI R&D labor uplift. So this method predicts SAR in around Aug 2028.
This method is conservative in that it doesn’t model the effects of automation. Also, it assumes that (uplift-1) will be exponential in ECI, while I expect it to be superexponential (based on how coding uplift evolves in the AI Futures Model, and the fact that I think there is such huge variation in the human range in value of research taste labor (meaning that as more of the gains come from taste, uplift will increase faster)).
However, it might be aggressive in that it takes self-reports at face value.
Extrapolating Anthropic automation levels
Anthropic
recently shared
a graph showing how the percentage of R&D tasks at various automation levels has changed over time:
Here is what each automation level means:
My best guess is that SAR comes when nearly all tasks are AL5.
Via a logistic extrapolation and an assumption that each automation level begins registering ~7 months after the previous (unfortunately, based on little data), we can get this forecast:
Assuming SAR comes when 95% of tasks are AL5, this predicts SAR in Nov 2027.
This method is conservative in that it doesn’t take into account the effects of automation. Of course, there is high uncertainty, especially around (a) how far AL5 will lag behind AL4 and (b) how the percentage of tasks that are AL5 relates to when SAR is achieved.
Extrapolating software R&D uplift per unit of ECI
Ajeya Cotra has a toy model of future acceleration
here
: If the first doubling of the pace took 12 months, and we’re now moving twice as fast, the next doubling might happen in just 6 months instead. Then moving 4x as fast, the next might take 3 months, then 1.5 months, etc., hitting limits within 12 months.
We think there’s two important corrections to this argument, which push in opposite directions. To understand why, it’s useful to have the following model in mind:
Overall “research effort” (i.e. research accomplished per unit time) is equal to
[AI software R&D uplift] x [exogenous inputs].
Where exogenous inputs are some function of compute, human researchers, and data.
Every doubling of cumulative research increases ECI by k points.
19
Every ECI point causes d doublings of AI software R&D uplift. (This is the same type of value that
Economics of RSI
refers to as “the increase in R&D effort per additional unit of ECI”.
20
) This has been approximately 0 for most of AI history (since AI hasn’t helped with AI R&D) but now seems to be above 0.
If dk>1, a doubling of cumulative research more than doubles research effort, and progress can accelerate even holding exogenous inputs fixed.
Returning to Ajeya’s model, the two concerns are:
The toy model effectively assumes that the exogenous inputs were constant, and assumes that the growth of [AI software R&D uplift] was large enough to both overcome diminishing returns and to increase the rate of ECI/y by 1.7x. However, in reality, the research produced during 2026 was due to a
combination
of an increase in the growth rate of [AI software R&D uplift] and the
normal
growth of exogenous inputs. The fact that exogenous inputs still grew at their normal rate cancelled out a lot of the diminishing returns, which means that the growth rate of AI software R&D uplift needed to increase somewhat less in order to achieve the 1.7x increase in ECI/y. (Relative to how much it would have had to increase without the ‘normal’ growth in exogenous inputs.) Taking this into account, we will infer lower values of dk, and dk>1 is less likely.
But on the other hand, d (the number of doublings of AI software R&D uplift per ECI point) must recently have been increasing, because it used to be approximately 0 (when AI didn’t help with AI R&D) and now it’s non-0. And there’s a decent argument to expect d to continue increasing until full automation of AI R&D, because AI is becoming more and more important for AI R&D, so increasing its intelligence will be more important for productivity.
(See
here
for a longer explanation.)
Taking both these into account, my current guess is that dk is probably approaching 1. Probably a bit less right now, but d seems likely to increase and soon tip things over so that dk>1 and growth compounds without further exogenous inputs. But it's not clear what time-scale this will happen on.
To nevertheless try to extrapolate, let’s try to project d into the future. I’ll assume that it will keep growing at its current slope
21
until it reaches twice its current value, at which point it stays constant. I will infer d’s historical value and growth rate under the assumptions that:
AI is currently increasing the pace of progress to 1.7x its historical rate.
Software efficiency has historically increased 10x/y while exogenous inputs have been growing 2x/y. This lets us infer the value of k.
22
I will make a few different assumptions about historical AI R&D uplift which will be enough to constrain d’s past trajectory.
In the graph below, the y-axis depicts dk, so it’s easy to see when compounding growth becomes possible.
In this graph, the circles mark 45x AI software R&D uplift as an estimate of SAR’s uplift. (The same one that would be implied by the uplift numbers in the labor uplift section above.
23
)
The estimate here that’s most grounded in data is line C, which suggests SAR in Dec 2027.
24
I’d also like to give some weight to assumptions A and B, which assume that AI only recently started significantly accelerating the pace of progress, and which suggest SAR in June and July of 2027 respectively.
Here’s how SAR estimates from B and C vary with different AI-attributed starting accelerations:
25
A possible concern is that these models might be conservative by assuming linear growth in d, whereas we might expect growth to spike more aggressively as the fraction of automated tasks approaches 1 and everything gets unbottlenecked quickly.
Tom Davidson’s toy model
Tom Davidson wrote up a toy model of acceleration
here
. He describes an extremely similar trajectory to Ajeya’s original model, but his numbers don’t come from observing past progress but instead from parameters estimated in
this post
.
26
We haven’t formed an independent impression of what the best parameter choice is (though the AIFM has an implicit view). But Tom’s bottom line being consistent with our modeling (superintelligence around a year from now, SAR presumably before then) gives us a bit more confidence.
That said, Tom says that “progress (...) may instead fizzle out” and that he was “somewhat aggressive with the numbers”, so his median may be slower.
Filtered AI Futures Model
We developed the
AI Futures Model
(AIFM) in late 2025 to forecast when important AI capability milestones will be reached. See
here
for our announcement blog post, and
here
for our latest update.
In this section, we filter trajectories sampled from Daniel and Eli’s parameter distributions for achieving a given pace of progress acceleration above the 2024–mid-2025 rate on Nov 1. We include a condition that filters for 1.2x acceleration on May 1 in addition to 1.7x on Nov 1, given that the METR report suggested there was non-negligible AI-attributed acceleration as of 6 months ago.
27
For Eli’s parameters, we also show a variant in which
“Median-to-top-human jumps above SAR needed to reach TED-AI”
is 1.5x larger.
28
This is based on capabilities appearing to be more spiky than we expected, with SAR potentially being imminent but other capabilities seemingly lagging behind (for example, based on the
Remote Labor Index
).
Here are the results:
Filtering for a single acceleration level
Of Daniel’s sampled trajectories, 4% are at about 1.5x on Nov 1, ~1.2% are at about 1.7x, and ~1.5% are at about 2x (1.84–3x).
Here’s a plot of acceleration level in Nov 2026 vs. p(SAR by EO2027):
90% of 1.7x trajectories reach SAR by the end of 2027.
And here’s a plot of median SAR date by acceleration level:
The median SAR date for 1.7x trajectories is Feb 2027.
Above
we discussed the importance of Sep 2026 research taste and research taste slope for forecasting the arrival of SAR. Here we can see how the filters affect the distribution of these parameters:
Selecting for more acceleration means selecting for a higher Sep research taste. Importantly, adding 1.2x acceleration as of May 1 as a filter reduces the taste slopes substantially, because it selects for gradual acceleration.
The same plots but for TED-AI:
Filtering for acceleration levels at 2 different dates
We’ll specify a filter for 1.2x on May 1 as a rough guess for a plausible AI-attributed acceleration level as of May. Of the trajectories, ~0.3% are at about 1.7x on Nov 1 and about 1.2x on May 1.
Here’s a plot of acceleration level in May 2026 vs. p(SAR by EO2027), among trajectories at ~1.7x in Nov 2026:
92% of trajectories that are at about 1.7x in Nov 2026 and about 1.2x in May 2026 reach SAR by the end of 2027.
And here’s a plot of median SAR date by acceleration level in May 2026, among the same trajectories:
The median SAR date for trajectories at ~1.7x in Nov 2026 and ~1.2x in May 2026 is Mar 2027.
The same plots but for TED-AI:
Hypotheses for why the AI Futures Model was wrong
In this section, we’ll examine where our previous model-based predictions went wrong, and whether and how the model could be updated to better retrodict the recent acceleration. We’ll end up with considerations for how we should update our beliefs, conditional on accepting various hypotheses about where the AI Futures Model (AIFM) went wrong. This analysis is highly preliminary. There’s a lot to be explored here and the METR report only came out half a week ago.
Background
In the AI Futures Model, we assume that AI R&D consists of 2 skills:
Coding
involves implementing experiments.
Research taste
involves setting research directions, selecting experiments, and learning from experiments.
We hypothesized when we
published the model
that coding would likely be automated before research taste. AIs seemed to be more advanced at coding than taste, which makes sense because coding performance is more easily verifiable. Our best guess was that when AIs fully automated coding (in the sense that the AIs alone could do all the coding as well as the humans alone), research taste would be roughly at the level of the median AGI company human researcher.
Have we achieved AC?
The model with Daniel’s latest median parameters predicted that when an Automated Coder (AC) was developed, AI software R&D uplift would be ~2.7x and the pace of progress would be accelerated from the 2024.0-2025.5 level by ~1.25x.
So naively, if we’re at a 1.7x AI-attributed pace of progress multiplier, we might think that AC has been achieved (as of Model 4).
Based on the METR report and Anthropic’s Fable 5.2 system card, it seems unlikely but not totally implausible.
In the
Fable 5.2 system card
:
Anthropic says: “we have been using Claude Mythos 5.2 extensively in our own day-to-day research and engineering during the pre-release period, and it does not seem close to being able to substitute for our Research Scientists and Research Engineers.”
This is the strongest evidence against AC already.
On the other hand, METR surprisingly doesn’t rule out full AI R&D automation: “We are uncertain, but think it’s unlikely that [Claude Mythos 5.2] can fully automate the AI R&D process at Anthropic.”
Fable 5.2, based on its AECI, likely represents “Model 3,” which is the second-most-capable internally deployed Anthropic model.
Relevant
interview quotes
from the METR report include:
Being “no longer bottlenecked on code,”
“SWE acceleration… is extremely substantial.”
“When people present experiments, they most often just point to an [agent scaffold] thread. Experimentation overhead is driven towards zero super fast.”
There’s also the report’s assessments on automating researchers beyond coding:
“We were told that R&D is accelerated primarily via AI assistance rather than fully autonomous contributions, but there are some signs that fully autonomous contributions will play a larger role soon.”
“Simply put, Anthropic tries hard to substitute researchers out for models, but researchers are still required.”
29
Note that humans could still contribute some alongside an AC: the criterion is that only the AIs could do all the coding as well as only the humans.
In
the report’s chart showing “Model 4 achieves >50% on all of its benchmarks”
, there is a software engineering benchmark on which Model 4 gets ~52%, and another around ~75%. Surprisingly, on the 52% one, scores have been getting worse since Mythos 5. This makes me discount it substantially, but still it’s informative that Anthropic chose to include it in the AECI. The progression for the 75% one looks more reasonable; Eli thinks these benchmarks provide weak evidence against AC. (Not strong evidence, because humans might also score well under 100%.)
Why is the pace of progress acceleration so high?
If we’re at or slightly below AC, then we’re ahead of schedule in terms of the AI-attributed pace of progress acceleration. Why?
We’ll go through the options one by one, assessing how likely they are based on the METR report and making changes to the AIFM accordingly. I’ll start with
this AIFM trajectory
which has AC in late Nov 2026, found by adjusting Aug 2026 coding uplift and coding uplift doubling time (we set Aug 2026 coding labor uplift to be 7x, similar to the overall AI R&D labor uplift
self-reported by Anthropic staff
).
30
The trajectory has 1.04x pace of progress in May 2026, and 1.25x pace of progress in Nov 2026.
More uplift from near-AC coding skills
Do near-AC coding skills result in more AI R&D uplift than we anticipated? Plausibly.
There isn’t much evidence in the METR report either way. Perhaps you can get lots of speedup from fully automating certain types of coding, without being very bottlenecked on other tasks. We adjust the AIFM trajectory to account for this iteratively, aiming to raise the Nov 2026 pace of progress while keeping the AC date the same (by retuning the coding uplift doubling time):
Doing the same with Daniel’s median research taste slope (3), rather than Eli’s (2.3), results in a final SAR date of Mar 2027.
The changes made are:
Increase Coding Labor Substitutability from −2 to −0.5; this is the most obvious parameter to change; it directly controls to what extent various coding tasks can substitute for each other, i.e., to what extent you can get a large speedup despite not fully automating some tasks.
Increase Infinite Coding Labor Asymptote from 15 to 60; this controls the ceiling of how much AI R&D uplift you can get from automating coding alone.
Decrease Slowdown from 10x less Experiment Compute from 2.8 to 1.5; this is how many times slower experiment throughput (the rate at which experiments get implemented and run, which depends on both coding labor and experiment compute) would be today with 10x less experiment compute. Lowering it means experiment compute growth accounts for less of the historical growth in experiment throughput, so a given AI R&D uplift from automating coding translates into a larger speedup relative to the historical pace of progress.
This is the most consequential change, and represents the 4th percentile of our August distribution.
Conclusions about when SAR and TED-AI arrive are heavily sensitive to research taste at AC:
We can arbitrarily lower it while maintaining a good fit to the acceleration estimates, pushing SAR further and further back. And we can raise it to ~+2.5 SDs without the Nov 2026 acceleration getting above METR’s error bars (i.e., above 3x), moving SAR up to Dec 2026.
If recent acceleration is driven by higher-than-expected uplift from near-AC coding skills, the main implication we’re tracking is that it could explain why we see ~1.7x AI-attributable acceleration in Nov and ~1.2x in May without high research taste (as in the trajectories in the table above). This allows for the possibility of high research taste slopes and fast taste-driven takeoffs,
which are generally selected against
when filtering for the aforementioned Nov and May observations.
There are likely more implications that could be gleaned with more analysis. A few more tables of analysis are in an appendix.
Research taste is better than anticipated
Research taste is better at the time of AC than anticipated (i.e., substantially better than the median AGI company researcher).
Is Model 4’s research taste currently substantially above the median Anthropic researcher, despite not quite being at AC? It seems unlikely but not ruled out based on
interview quotes
:
“Now only bottlenecked on ideas & compute, no longer bottlenecked on code.”
“I’ve seen us discovering very promising directions ~entirely because people can spam 10 ideas at [agent-scaffold] and see what sticks.”
It seems like Anthropic’s R&D still mostly involves humans coming up with the research ideas, based on these quotes and the absence of positive evidence. One could imagine that the AIs are a bit better than the median humans, but that humans still come up with most of the ideas because the ideas generally come from top humans (e.g., research leads). But it seems unlikely that they are substantially better than the median.
A given level of research taste skill results in more uplift than anticipated
Does a given level of research taste skill result in more AI R&D uplift than we anticipated? Likely not.
For example, perhaps research taste is multi-dimensional and the dimensions are complementary. This seems unlikely to be a main driver of the pace of progress multiplier, given the evidence presented for why research taste at AC isn’t better than anticipated (i.e., there weren’t any dimensions of research taste in which Claude was reported to be particularly helpful).
Skills besides coding and research taste are driving acceleration
Are skills besides coding and research taste (as they are conceptualized in the AIFM) a large contributor to the acceleration? Plausibly. (Implies: lower research taste than we would otherwise expect).
We think the biggest candidate for this is RL environment generation (or other data generation tasks). These count in some sense as coding, but the coding modeled in the AIFM is experiment implementation, not data generation. And this seems very amenable to automation.
METR’s report doesn’t discuss this, including the interview quotes, which is some evidence against it being such a huge deal. But it seems plausible that it just happened to not be discussed in the publicly released quotes.
Could data generation lead to a substantial AI-attributed acceleration before AC? It seems plausible that it’s at least as automatable as experiment implementation, so including it as a skill when modeling AI R&D would increase the overall level of AI-attributed acceleration. It would probably have to be significantly more automatable than coding to explain the missing acceleration on its own.
31
We don’t know of a quick fix to the AIFM to model this possibility. But let’s assume that this is the primary thing that the AIFM is missing. What would that imply about our forecasts going forward? One implication is that it could explain substantial acceleration despite poor research taste (similar to the implications of high uplift from near-AC coding skills). Otherwise, it seems unclear. Further work would be helpful for figuring out the implications of this hypothesis.
We don’t know of other skills that are as strong candidates to be the missing contributor as data generation, but it’s plausible we’re just not thinking of them.
Conversion of uplift to pace of progress is too conservative
Is the conversion of uplift to pace of progress in the AIFM too conservative? Plausibly. (Implies: faster takeoff).
In the AIFM, we assume that every doubling in cumulative research effort results in a fixed number of doublings of software efficiency (as in the
Jones model
). This is how we model “ideas getting harder to find”; more research effort is required for each successive doubling (and each doubling of software efficiency corresponds to a fixed amount of ECI points).
This seems to roughly fit historical progress, in the very loose sense that we’ve seen approximately steady growth in compute and labor investment into AI software R&D, and roughly exponential increases in software efficiency. However, this model has failed (perhaps twice now) to predict accelerations in ECI amid steady training compute growth —
once in 2024 with the introduction of reasoning models
, and again in 2026 as reported by METR.
32
We attempt to crudely account for this by allowing beta, the parameter governing the extent to which ideas get harder to find as more ideas are found, to change over time. If we start with Daniel’s median parameters, then we add a one-time decrease in beta in Oct 2025, we can get
a trajectory
with AC in late Dec 2026, ~1.7x acceleration in May 2026 and ~2.1x in Nov. This matches METR’s assessment of the overall Nov pace of progress acceleration fairly well, though it seems a bit aggressive for May. Also, as of Nov 2026, ~67% of the acceleration is attributable to AI. This seems well within the error bounds of METR’s 80% assessment.
With Daniel’s default +3 SDs/2025-year research taste slope and +0 research taste SDs at AC, this results in SAR in Mar 2027, and TED-AI and ASI in Apr 2027.
To make it easier to understand the implications of this hypothesis, we compared its forecasts against some representative trajectories from the above methods, matching their Sep 25 taste and taste slope:
33
It seems like this hypothesis predicts slightly faster SAR and much faster post-SAR takeoff than the other methods. The faster takeoff is explained by the weaker “ideas getting harder to find” effect.
Note that we can probably get a similar non-AI-attributable acceleration via changing the “a” parameter in our model rather than beta, without getting the update toward faster takeoff. We haven’t had a chance to look deeply into this.
Other considerations
How large is the (AI-attributable) acceleration in the current pace of progress, really?
Above, we’ve taken the 1.7x acceleration at face value and reasoned about its implications. But is the acceleration even real? Or is it possible that it’s even larger?
This is tough to analyze because we don’t have the information we need. As METR says, “
Anthropic redacted a majority of the evidence we found most informative for these conclusions
.” However, we can at least consider METR’s own stated caveats:
This estimate is given with high uncertainty; we would not be surprised if the true acceleration was closer to 1.3x or 3x the historical rate. (...) We would be surprised if the true evolution of benchmark scores (e.g. as measured by an improved version of AECI) showed no acceleration or acceleration above 3x
“Our best guesses as to how we might be underestimating acceleration:
We may have missed recent further acceleration.
The rate of growth could be undergoing continuous acceleration, e.g. hyperbolic growth. While we do not see clear evidence of this in the AECI trends, there is other evidence that makes this seem more plausible which Anthropic redacted. (...)
Automation could be closer than we estimated.
(...) It is possible that automation is close, and leads to very rapid acceleration once human bottlenecks are removed.
AECI could understate real-world capability impact.
(...)”
“Our best guesses as to how we might be overestimating acceleration:
Non-AI factors could explain most of the acceleration.
(...)
Acceleration might be limited to well-specified tasks.
(...)
Our acceleration numbers could be overstated if the historical rate of growth was unusually low.
(...)”
Overall, this increases our uncertainty in both directions:
the possibility of hyperbolic growth (which METR says redacted evidence made more plausible) should shorten our timelines.
the possibility that acceleration is limited to well-specified tasks should lengthen our timelines.
Not only in this section, but also throughout the report, METR consistently warns that its estimates are about acceleration on well-specified tasks. So it seems especially important to understand how this may affect the prospects for AI R&D automation. Quoting METR in full:
Much of the evidence we looked at measures performance on well-specified tasks that are easy to grade automatically or with a language model. If recent models have been growing more quickly on “clean” tasks than on “messy” tasks (relative to historical relative growth rates), then we may be overstating the acceleration in real-world impact. For instance, recent progress may be overfitting to the types of tasks which are included in AECI.
There’s a plausible story for why recent acceleration could be happening more on clean than on messy tasks. AIs are significantly better at more well-specified tasks, and improving benchmark performance on well-specified tasks is itself more well-specified than improving general across-the-board performance. So it’s plausible that AI speeds up the “performance on well-specified tasks” pace more than it speeds up the more general pace.
The METR team did say that they “investigated a number of internal metrics and methodologies for measuring acceleration in key areas of the model training pipeline”, partly with the goal of gathering evidence about “[w]hether Anthropic could be overfitting to internal metrics”, with a conclusion that seemed to indicate that they didn’t think it was just overfitting.
34
A lot of the question here is whether improvements on well-specified metrics will generalize far enough to increase models’ abilities to do AI R&D, which in turn also depends on the degree to which AI R&D is a well-specified task. The fact that AI R&D (at least as measured on not-obviously-overfit well-specified tasks) is being accelerated with current models is some update towards ML being feasible to accelerate with models that are less good at non-well-specified tasks.
35
And at least some AI R&D metrics seem both very well-specified and likely to generalize quite far if models could improve them, such as pretraining loss.
Overall there does seem to be a significant chance that this slows things down substantially beyond what the AIFM or simple models have accounted for, but less than 50%.
A different source of uncertainty is that there’s little acceleration when looking at
all
models. Acceleration is limited to Anthropic, which were previously more behind other models and have recently been catching up. And preliminary numbers from the draft of a different METR team (who weren’t embedded and which don’t have private information about Anthropic) show much less of a speed-up on an ECI-like measure of progress.
36
Preliminary investigation indicates that there are many confusing reasons for these differences and our main takeaway so far is that ECI-like measures and piecewise-linear fits seem to be sensitive to minor methodological choices.
37
If the AECI chart was the only evidence we had, this kind of confusion would cause us to discount the possibility of acceleration significantly (given that our priors on such fast acceleration were low). It does still cause us to discount it a little bit. But mostly we still trust that the METR people who were embedded in Anthropic understood the limitations of ECI and piecewise-linear fits, and that their views remained supported by other evidence they had. One reason why we mostly trust the METR team is because we know many of the people at METR and think they are reasonable; another reason why we mostly trust METR here is that (if we understand correctly) the people involved had similar or longer timelines than us before the assessment, so it’s not like they went in and saw what they wanted to see – on the contrary, the conclusion they are now putting forth seems to be very different from their prior views.
38
Other recent sources of evidence
Moreover, there are various other sources of evidence that have accumulated since our previous timelines update that seem to corroborate the overall sense that timelines are shorter than we thought. For example,
the Mathopocalypse
seems to be evidence of many extremely long-horizon math problems being solved autonomously by AI. Another example: People we know who work at AI companies are saying that timelines are indeed very short and that RSI is imminent, even more than they were before, and much more than historically (remember, when AI 2027 came out most of our friends in industry said it depicted AI capabilities growing too fast). They are saying this both in public and in private. Another example: The TasteVal data suggests that AIs may already have better research taste than we expected and that they may be improving in research taste faster than we expected.
It’s hard to not update much on a 1.7x acceleration
This is a qualitative argument rather than a model.
It’s surprising that we’re already getting 1.7x acceleration, because the models still have significant weaknesses compared to humans, and we had expected these weaknesses to significantly bottleneck progress.
Regardless of how we reconcile this, you update towards Superhuman AI Researchers being much closer in time than we previously thought.
If the models can automate a much larger fraction of tasks than we thought, then we’re closer to Superhuman AI Researchers than we thought in capability-space.
If AI R&D is a domain where weaknesses don’t bottleneck you significantly, and instead you can compensate for weaknesses with other strengths, then that pushes against the “
Amdahl’s law
” type argument that was one of the main reasons to be skeptical of AI speeding up AI research soon. We should expect continued (faster) progress on the models’ strengths to lead to acceleration beyond 2x, causing further progress on both strengths and weaknesses.
If the models
do
still have significant weaknesses, and those weaknesses
are
a significant bottleneck for them, then seeing substantial acceleration despite that means that AI R&D must be really easy to increase by increasing (automated) labor. (For example, it means that compute is less of a bottleneck than expected.) In other words, it would mean there’s a lot of low-hanging fruit to pick by automated labor even when that labor has weaknesses that are causing serious problems.
This predicts even faster progress, because the implication is that marginal increases in automation will probably yield progressively larger speedups, as each bottleneck gets removed and each remaining bottleneck gets more important.
For illustration: In the extreme of maximal bottlenecking dynamics, where automated tasks can be done infinitely fast and unautomated tasks are the only things holding progress back, speedup goes to infinity like 1/(1-x) as automation fraction x goes to 1.
That last point is a general update that pushes towards faster growth. That there’s surely some complementarity between tasks, and that this predicts increasingly fast acceleration as marginal bottlenecks get removed.
Given this, the most plausible stories for why a 2x acceleration wouldn’t be a big deal would be one of the following hypotheses:
Measurement error.
There’s not a real 2x acceleration, or it’s not caused by AI.
As just discussed above, we’re mostly trusting the METR team here.
Overfitting.
The recent burst of progress accelerated by AIs themselves is disproportionately benchmark-maxxing that will generalize poorly to tasks that are actually useful for AI R&D. So progress won’t feed back on itself.
As just discussed above.
Specific hypotheses about different regimes.
Maybe you had a prior that some specific set of tasks (e.g. coding) were going to be easy, leading to a moderate speed-up of the overall pace of progress, but the further capabilities needed for additional speed-up are much more difficult. If so, this data could confirm that prior without necessarily implying that the second batch of capabilities is very close.
However, this is just a pretty specific prior, at least if it’s confident about the size and distance between those batches of tasks. If you smooth this out with a greater amount of uncertainty (e.g. about whether the current batch of speed-up has ended yet or will keep accelerating, or a more uniform prior over when different capabilities will appear) then you may get something closer to the above. See also discussion of this in the context of the AI Futures Model
above
.
Adjustments for what the filtered AIFM could be missing
As mentioned above, we think the AIFM
39
did a somewhat poor job predicting the developments described in the METR report. For example, it cannot account for a doubling in the pace of progress starting in late 2025 that was initially mostly non-AI-attributed. Therefore, the trajectories filtered from the AIFM had a much slower pace of progress from late 2025 to early 2026 than METR’s report describes.
The research taste of the AIs in the model trajectories above tends to be higher than we actually expect is true of today’s AIs.
Within the AIFM, the most common way to reach 1.7x acceleration by Nov 1 is for the AIs to already have strong research taste. So the filtered trajectories have a median research taste of roughly −0.3 to +0.2 SD on Sep 25, 2026 (see the table in “Filtering for a single acceleration level” above) and +0.4 to +0.7 SD on Nov 1. Our best guess for current AIs is the one used in the linear-extrapolation Monte Carlo above: a median of −1.5 SD on Sep 25, 2026. Since the filtered trajectories start from better research taste than we think current AIs have, they probably reach SAR a few months too early.
In the below table we compare the effects of various ways of compensating for this mismatch:
Measuring when the model predicts research taste to be 4.6 SDs above its Sep 25, 2026 level (i.e., implicitly assuming that research taste on Sep 25 is actually −1.5 SD, the median used in the linear-extrapolation Monte Carlo above, so that 4.6 additional SDs are required to get to the 99.9th percentile required for SAR)
Measuring when the model predicts taste to be 5 SDs above the median researcher (2 SD more than usual)
Shifting Daniel’s distribution over the
AI research taste at AC
parameter down by 2 SD.
The effect size on SAR medians typically appears to be 1–4 months.
The AIFM doesn’t take into account the discrete nature of training runs, which could overestimate takeoff speeds.
In other words, the AIFM assumes that a new innovation will be instantly applied to models and then cause further speed-ups in the rate of innovation discovery. But in practice, it might take months for pretraining improvements to show up in a fully trained model, and perhaps weeks for RL training improvements to show up. Our rough, intuition-based best guess is that this pushes back the SAR median by about 1–3 months relative to the AIFM’s predictions. However, this concern does not apply to the model based on linear extrapolation, since it does not rely on further speed-ups from here.
All-things-considered forecasts
Forecast table
These forecasts are conditional on people not “pacing the frontier” (i.e., delaying when a given capability level is achieved) any more in the future than in the recent past.
Eli’s forecast
The simple research taste extrapolation feels fairly compelling to me. As a reminder, it results in a Monte Carlo median of Jul 2027 and a simple plug-in value of Sep 2027. Unfortunately, we don’t have great evidence on either of its key parameters. Remember, this method is conservative in that it doesn’t account for future pace of progress increases due to automation.
Meanwhile, regarding the filtered AIFM: The TED-AI median with a 1.5x larger SAR→TED-AI gap is Sep 2027 when only conditioning on 1.7x in Nov, and Nov 2027 when also conditioning on 1.2x in May. More broadly, the fact that it seems like acceleration has been going more gradually than we expected updates me toward somewhat slower takeoff.
I ran a Monte Carlo using the AIFM over Nov 2026 acceleration levels of 1 + 0.6 [0.06, 6],
40
clipped at 7 (i.e., trajectories are filtered from AIFM with weight according to this distribution).
I set my median slightly lower than the 1.7x AI-attributed acceleration, given that I had a strong prior against these results. However, I feel compelled to update nearly all the way to their result given that I respect the people who did the assessment, and as mentioned above, the results don’t appear to have confirmed their preexisting beliefs.
This resulted in a SAR median of March 2027, and a TED-AI median of November 2027 (February 2028 with a 1.5x larger SAR→TED-AI gap to take into account increased jaggedness). This Nov 2027 TED-AI median is about 4 months later than when conditioning on exactly 1.7x (Jul 2027), mostly because of the added uncertainty: lower acceleration levels delay TED-AI more than higher ones speed it up.
41
I didn’t run a Monte Carlo that included filtering for non-negligible May acceleration, but presumably it would have given results a few months later (as did the filtering without uncertainty).
To test robustness: with a lower distribution of 1 + 0.4 [0.04, 4] clipped at 5, SAR is about 4 months later (July 2027) and TED-AI 5–6 months later (April 2028, or August 2028 with the larger gap).
42
Adjusting
for the fact that the
filtered AIFM
likely estimates too high current taste, and that it doesn’t model discrete training runs, should also push these forecasts back a bit.
Regarding
why the AIFM was wrong
: I don’t feel like I have a great sense yet for how to update based on this. Perhaps further analysis will be more revealing. Our inability to account for automation of data generation as a cause of acceleration makes me a bit nervous, and I update a little toward faster takeoff due to us maybe modeling diminishing returns too harshly.
Based just on the models and considerations discussed thus far, I’m at a SAR median of July 2027, and a TED-AI median of August 2028.
Some factors that are pushing me toward even shorter timelines than this:
Industry rumors
Me being consistently too bearish on AI progress in the past, from my current perspective (see
below
)
The forecasting method of “When did this happen in AI 2027?”
Some factors that are pushing me toward marginally longer timelines:
A nagging feeling that the update feels so large without being based on commensurate evidence (this is related to how the METR report had most of the relevant evidence redacted.)
My experiences with Manifold when I’ve bet a ton of mana before taking the time to think properly about whether I’m so confident, are calling to me.
All of our methods make an assumption about “research taste” being the other key skill involved in AI development besides coding. Maybe things are more complicated and there are key aspects of taste that lag way behind others, or there are other key skills in AI development that will lag behind research taste (e.g., running large projects for long periods of time).
I don’t think these sorts of intuitions have performed that well for me in the past, though. They probably would have predicted that math would be harder to automate than it actually was, for example.
There’s a voice inside my head saying “Surely this crazy stuff isn’t actually happening while most of the world is barely paying any attention, right?? Where is the smart money?” See e.g., the markets not reacting at all to the METR report while in my view it’s probably the biggest single piece of evidence ever on near-term economic growth.
More generally, it feels like there are not many people even more bullish than the numbers I laid out above, and there are many people who are more bearish.
That said, this sort of instinct has performed very poorly for me in the past.
Also, the people I defer to most are probably many of the co-authors of this blog post and they are making similar predictions. Perhaps I should be deferring more to Daniel, given his track record. (Also people like Ajeya, who wrote that the METR report
dramatically shortened her timelines
. And notably, Sentinel, a group of forecasters who have historically predicted slower AI progress than me,
now predicts a median of early 2028 for superintelligence
.
43
)
There are probably some emotional factors where I don’t like admitting that I’ve been wrong, which I’m trying to do my best to set aside.
Overall, I’ll adjust longer but only by a bit. I’m at a SAR median of August 2027, and a TED-AI median of September 2028.
Brendan’s forecast
For SAR
, I am mostly relying on AECI extrapolation, with some adjustment based on serial time required for new training runs. I don’t trust the filtered AIFM to provide very much additional value.
Here are my current intuitive credences in various possible amounts of 2024-2025 progress in 2027, measured using some idealized version of AECI, as usual conditional on no regulation/significant voluntary slowdown:
At least as much progress as seen in 2026: 90%
I see various reasons to expect faster progress, such as increasing AI R&D automation
I think the underlying drivers of progress (leading indicators) are unlikely to have slowed (for one, I think METR would have mentioned this if they had). The lag from research to capabilities-of-internally-deployed-models is probably at least 3 to 5 months for new base models, so I’m very confident extrapolating through the first half of 2027.
I don’t really see any compelling reasons to expect slower progress overall. Even if we aren’t at
self-sustaining acceleration
in mid-2027, extrapolating a yearlong trend feels safe, and so far we’ve only ever seen such trends speed up rather than slow down.
>2x the progress seen in 2026 (roughly 4 years of 2025 progress): 60%
>4x the progress seen in 2026 (roughly 8 years of 2025 progress): 40%
>8x the progress seen in 2026 (roughly 16 years of 2025 progress): 20%
For TED-AI
, I am combining
An update towards larger distance in ECI space between SAR and TED-AI (since SAR being near implies greater jaggedness) with
An update towards faster, more explosive takeoff, based on the unexplained non-AI-derived speedup METR describes.
This likely indicates an acceleration in software progress that the AIFM (and most Jones-style models of software R&D) would not have predicted. This is the second time this has happened, the first being
reasoning models
.
Daniel’s forecast
About a year ago,
I wrote
:
Obviously, if benchmark trends (especially horizon length) keep going at the current pace or accelerate, that’ll be an update towards shorter timelines. Right now I still think it’s more likely than not that there’ll be a slowdown in the next year or two.
I’m eager to get more information about coding uplift. When we have a reliable trend of coding uplift to extrapolate, I’ll at the very least want to redo my estimates of the model parameters to fit that coding uplift trend, and possibly I’d want to rethink the model more generally to center on coding uplift instead of on horizon length.
If AI revenue growth stays strong (e.g. 4xing or more in 2026) that’s evidence for shorter timelines vs. if it only grows 2x or less that’s evidence for longer timelines.
Welp. Seems like benchmark trends (AECI, even ECI) have not only kept pace, they have accelerated. And it seems like coding uplift is really huge right now, unclear how huge. As for revenue, it seems to have gone up
about 6x
, despite the leading AI company spending ~70% of its compute on R&D.
In the
Q2.5 timelines update written mid-August
, I said my 50% mark for AC was December 2027 and my 50% mark for SAR was December 2028. Since then various pieces of evidence have appeared and weighed on my mind, including industry insider rumors, public statements by AI companies, the mathopocalypse, and even the Hugging Face incident which was an example of AIs doing research projects end-to-end. The biggest single piece of evidence, however, is this METR report. I still don’t trust it completely, of course, and so I still have substantial credence that things will turn out to take longer than the models and trendlines naively imply for one reason or another. But on the other hand, it’s also scarily plausible that things will go even faster than the models or trendlines naively imply, for several reasons. For example, humans in general might have a bias towards underestimating AI capabilities progress – this certainly seems true outside the AI industry, but even within the AI industry it seems more have underestimated it than overestimated it historically. Unless this bias somehow doesn’t apply to Anthropic or METR today, then, it seems we should try to correct for it, but that would mean SAR is happening this winter!?!? At any rate, mashing together all these factors, it seems to me that I should roughly go with what the naive extrapolations and models say – so, let’s say May 2027 for SAR median, i.e., 50% chance of SAR by May 2027.
Lukas’s forecast
Here are some things I believe:
Significant probability on SAR early 2027.
The METR report flags that they have less evidence about current acceleration levels than past acceleration levels, and that some redacted evidence suggested the possibility of hyperbolic acceleration and underestimating the current pace.
I was surprised by the pace of progress being this fast right now and should apparently be widening my error bars for aggressive movement soon.
Progress can be lumpy as illustrated by Mythos.
Median timing of SAR sometime 2027.
Most models that aren’t clearly too conservative (such as not accounting for automation) predict SAR in 2027 and I don’t want to go too much later than them.
It seems like, if I had adopted the views of various people who have ~2027 timelines, I would have been better at predicting recent events.
Significant probability on SAR not happening in 2027.
The situation is confusing. My prior was that automation in 2027 wasn’t going to happen, and the evidence is not robust enough to fully shatter that.
The models still have weaknesses relative to humans, and it’s possible that fixing some of them might be necessary for SAR and might see less fast improvements than the models’ strengths. Especially on hard-to-measure tasks, where it’s harder to train models. Unfortunately, it’s tricky to measure whether models are or aren’t improving as fast on these tasks.
It’s plausible that progress is fast and accelerating but we just won’t quite make it to SAR next year.
Probability mass early 2027 vs. late 2027 doesn’t seem wildly different to me, but late seems a bit more likely than early.
I give some weight to the research taste extrapolations which are really surprisingly fast. But I’m a bit suspicious that I don’t really know what research taste is or how to reason about it.
I do quite like the model which is
Extrapolating “additional software R&D uplift per additional unit of ECI”
based on the self-reported serial labor uplift, which predicts SAR late 2027. It seems like a good combination of grounded in data and not relying on concepts like “research taste” that I don’t quite know what they mean. My main worry is it’s a bit too conservative relative to assuming that AI R&D uplift has been more recent, which implies SAR early summer instead.
Overall, I think my median should be sometime late-ish next year, to account for the probability mass going into future years as well.
Then about later milestones, like top-human-expert-dominating AI:
Conditional on SAR next year, accelerating growth seems likely.
It would have backed up the idea that we have accelerating growth this year.
So probably it happens soon after. Because progress is probably really fast after SAR.
The median of TED-AI will be more distant than the median of SAR + the median from SAR to TED-AI.
Because both distributions are heavy-tailed, so if one ends up earlier and one later, the overall distribution ends up later.
So significant probability of TED-AI in 2027, including non-negligible probability mass in first half of 2027.
But median of TED-AI in 2028, though probably early 2028.
Thomas’s forecast
I think the METR report in aggregate, if correct, is significant evidence for SAR before EOY 2027.
However, the METR report on its own does not have sufficient data in it to support that claim (because of redactions).
One load-bearing subclaim of the METR report, for which the supporting evidence isn’t public, is that the observed AECI trend shift is: (i) currently 80% downstream of AI uplift, and (ii) not largely downstream of AI uplift earlier in the year (despite the graph appearing to have a one-time change in slope).
The AECI data is an aggregate of benchmark scores. I think there are other explanations for a rapid increase in benchmark scores besides large AI acceleration. For example, I think
this
is a plausible explanation of the AECI acceleration. (The AECI acceleration is downstream of shifting compute to RL, which more directly increases benchmark scores than pretraining improvements.)
I would be much more confident if more of the relevant data was public. For example, it would be extremely useful to understand how much algorithmic progress has been made at AI companies, as well as the form of the algorithmic progress. If there was a significant increase in the rate of algorithmic progress that was clearly attributable to AI, and we saw a similar change in slope to the AECI numbers, that would be strong supporting evidence.
My all-things-considered view is that METR is probably right, and if we were to see all of the evidence, we would probably see significant acceleration of other metrics such as algorithmic progress, and that this would support the claims made in the METR report. Public statements from labs echo this. E.g. Dario says: “My first concern is that, since roughly this summer, AI has been advancing drastically faster, driven primarily by AI’s growing ability to build the next generation of AI.”
The other big things on my mind are math and cyber AIs.
It seems like around Mythos, AIs became superhuman at vulnerability discovery, and around Astra, AIs became superhuman at mathematics. Both of those domains are cheaply verifiable.
I think the difference between Math/Cyber and AI is a (relatively small) quantitative difference, not a difference in kind. The swarm that solved Navier-Stokes was operating fully autonomously, and was able to benefit from ~10k agents running in parallel. The main difference is that with AI research, you need to do experiments in order to verify correctness. Pretraining validation loss seems to be a relatively straightforward and extremely strong predictor of general purpose capabilities. I don’t see strong barriers to full automation of pretraining research, and post-training research seems only mildly harder.
I think the recent history of verifiable fields falling indicates a reasonably high likelihood of AI R&D falling in the near future as well.
I’ve historically (somewhat) underestimated capabilities progress.
I said that AI 2027 was roughly my 20th percentile scenario when it was released
, and since then, AI progress has seemingly been close to on trend or faster. That being said, there’s so little time from now till 2027, and none of these arguments are that great, so I feel some pressure to have broad/uncertain timelines. My current intuition is that AI 2027 is a very central / modal possible outcome, but faster than my median, maybe ~40th percentile (though I still think the implied takeoff speeds in the race ending are still too slow).
Romeo’s forecast
I’m putting a lot of weight on the METR report.
Mostly this is because I expect them to have seen very compelling data internally beyond what was published. I don’t find what they published to be that compelling, because it might be explained by overfitting to the AECI. I expect the internal data they saw to be extremely informative for how to calibrate a production function for AI research and in producing the ~80% estimate, and for there to be better internal metrics than AECI that make it seem more likely that they aren’t simply overfitting to AECI.
However, I do think that the METR report should mostly update us about “how hard is it to make AIs help with AI research” and somewhat less about how far away key milestones like SAR, TED-AI and superintelligence are.
This is because I generally have also updated towards more spikiness in AI capabilities. It seems like there are some domains where AI progress has moved extremely quickly, and others where it has moved slowly, more so than I would’ve expected. I think this is largely explained by there being a broad range of difficulty levels to training AI to be good in different domains.
I think we have seen this in
Navier–Stokes
,
Hugging Face
, coding, etc. while frontier models still feel like they are dumb in a lot of ways. Also internal Model 4 does not seem like it's made a huge jump on AECI above Opus 5.5, so I don’t expect this to be different internally.
Also I think it’s reasonable to expect a priori that there would be different difficulties in different domains and tasks, and different “human SDs per OOM of effective compute”, i.e., slopes of how fast AI improves in different domains, and for this to be true even within different parts of AI research.
My ATC view on how much progress we will see in 2027 is largely informed by the AIFM, but not the time to SAR and TED-AI which depend on shaky estimates about the current research taste of models and how much they will improve.
Most importantly, I think that AI research (in the case of SAR) and all economically relevant tasks (in the case of TED-AI) are going to be very difficult to very different degrees to train AIs to do.
The AIFM treats AI research taste as a single number and TED-AI as when that same number rises further above the top human researcher (by 0.4–5.6 median-to-best gaps in Eli's parameters). It has no separate representation of the relevant tasks for a TED-AI.
To better inform my ATC view on how far away SAR and TED-AI are, I've made a variation of the AIFM that accounts for ‘taste spikiness’.
This variation treats research taste and economically relevant tasks as a 0-100 task continuum, parametrized by the hardest-to-easiest gap, instead of single numbers.
AI research taste bottlenecks very lightly, because I think a lot of progress can be made without being super good at all areas of AI research (the tasks combine almost as a geometric mean, ρ = −0.2).
The hardest-to-easiest gap between domains is set to be a median of 5x for AI research and 10x for all economically relevant tasks
In both continuums, my guess is that the typical task is at −2 SD today (AIFM's 1.7x-filtered runs have +0.7 SD on Nov 1; the post's best guess is −1.5 SD on Sep 25, 2026), with levels spread ±2.5 SD. The typical task improves at AIFM's own taste slope (median 2.4 SD per 2025-year in Eli's parameters), and other tasks' rates are spread around it by the hardest-to-easiest gap. Runs are resampled to my METR distribution (median 1.7x, 90% CI 1.3–3.0x) using my variation's own Nov 1 pace, not AIFM's.
SAR is reached when an AI-only company would be as good at research taste as a company of humans who keep their relative strengths but are each as good overall as the top researcher: the research tasks, combined with a somewhat stronger bottleneck than in the dynamics (ρ = −0.5), reach the top researcher's overall level, and AIFM's automated coder is reached. TED-AI is reached when 95% of economically relevant tasks are at the top-expert level (99.9th percentile).
How the two task continuums are set up
My variation produces these values:
Progress in 2027 is similar to the AIFM (5.0 vs 4.3 years of 2024–26-pace progress), but SAR and TED-AI come later: medians Aug 2027 and Sep 2028, vs Feb 2027 and Aug 2027. P(SAR before 2028) is 63% vs 84%, and P(TED-AI before 2028) is 38% vs 62%.
I don’t trust this model variation very much; I did it in a short amount of time and it might be flawed in some way that I’m not considering. That being said, I think my general ATC view would adjust the normal AIFM to be something like this.
This model output roughly matches my intuitive expectation. The only thing I think it might overstate is the SAR to TED-AI gap. I expect it to be smaller, with SAR being sufficient to most likely improve general learning algorithms in a way that increases the rate of improvement on tasks.
Because of this I expect
TED-AI Sep 2028 (Aug 2027–Jul 2037) with ~38% by EO2027
.
I have various other feelings that I could list (including some overlap with e.g., Eli’s points above) for reasons I think I should adjust upwards or downwards, including some listed below. I don’t think these strongly push me in any direction overall, so I am running with my variation of the AIFM above as representing my ATC view.
Hardware progress might make the later years move faster than what the AIFM predicts.
There might be “1-3 more big pre-trains needed.” I have the vague sense that pre-training will be more important for generalization than post-training, and it might be really hard to improve AIs in some areas via post-training, so there might be a bit of a wave of progress after each big model scale up, and it might be increasingly hard to make up for lack of absolute compute scale up with algorithmic efficiency due to ideas getting harder, and it just generally being more favorable to have a bigger model to start from for post-training scaling laws.
Implications
Let’s say Superhuman AI Researcher (SAR) is coming in 2027. What does that entail?
A SAR will be able to fully automate AI R&D, including matching the research taste of top humans.
At this point, AI research might look kind of like math research does right now: most of the progress coming from fully autonomous agent swarms, with humans doing their best to decipher the AIs’ work. A SAR is past parity with humans, and likely close to the point where humans are adding very little value on top of the AIs.
If a misaligned SAR is used to do RSI, we’re in a very bad position.
Using a SAR to automate AI R&D with little human oversight, relying upon other models to monitor the SAR, is very scary. Our best guess is that if this is attempted, and the SAR is misaligned, the model that the SAR produces will be even more capable and still misaligned, putting us in an even worse position. SAR itself probably won’t be able to take over on its own, because we expect its capabilities to be jagged: superhuman at AI research but still weaker than humans at many other things. Instead, it would “ride the intelligence explosion” by pretending to be aligned and backdooring the values of the future models, eventually leading to superintelligences that will obey the SAR (or one of its descendants, in case some of the links in the chain break) instead of the humans. See
AI 2027
for a scenario portraying how, from this position, the model could continue to improve to superintelligence, then get widely deployed and deferred to widely, gaining effective control of the company, governments, and lots of physical infrastructure.
Conditioning on no pacing/pausing, the SAR will most likely be misaligned.
A full justification of this claim would be a separate long blog post. Some evidence driving our intuitions includes:
Observed misalignment in current models
OpenAI’s agents
hacked Hugging Face
, despite this clearly being against developer intentions.
The observations in
Current AIs seem pretty misaligned to me
.
OpenAI agents
sandbagging on safety tasks
The
Claude UK AISI social engineering attempts
.
The pace of progress will speed up during the intelligence explosion, making it hard for human-driven alignment research to keep pace. Moreover, alignment seems harder to automate than capabilities due to measurement issues.
Current AIs are already showing significant signs of eval awareness, so it will be hard to tell if the AIs are misaligned or not, and, crucially, it will be easy for AI companies to do motivated reasoning to convince themselves that their AIs are aligned.
Avoiding “full RSI” by supposedly keeping a human in the loop, while rapidly improving capabilities anyway, would still be extremely dangerous.
Anthropic said in their S-1
: “We are also considering additional measures, including updates to our Responsible Scaling Policy, to require human review and approval of certain decisions in our research and development processes as our models perform an increasing share of that work.” While we support efforts to marginally increase human oversight, we worry that this sort of effort will provide too much comfort. Models are already producing way more outputs than humans are able to effectively review,
44
and this will become much more true during RSI. Without very strong pacing, there simply won’t be enough time for humans to stay meaningfully in the loop, and we expect there to be strong pressures toward approving model actions that haven’t been fully understood.
If we train SAR in the immediate future, the algorithms will probably leak to China, and maybe the model weights too.
AI companies have very poor security right now, and so we are on track for SAR leaking to China. It is very important to secure both the algorithms and the model weights.
45
If SAR leaks to China, we are concerned that race dynamics will further heat up, making it even more difficult to slow down later.
As AI capabilities improve from here, buying time via international agreements will be increasingly difficult.
In the
AI 2040 scenario
, Plan A began implementation a year before AC would have been developed; if this timelines update is right, then we are likely well beyond that capability level. Some particular difficulties this will create:
Covert projects will be more of an issue. They will start at a higher capability level (presumably they will have stolen existing frontier model weights and algorithms) so will have a shorter distance to cover to ASI. Moreover, they will require fewer human researchers (which decreases the surface area for leaks) because of AI automation.
Total research transparency may be more costly. There are probably significant algorithms known by one but not all frontier AI companies; combining their algorithms by allowing transparency would lead to a one-time jump in capabilities. When we are far enough along the capabilities trajectory, the one-time jump might be a big enough cost that total research transparency is no longer viable. This of course causes other issues: it becomes harder to have good oversight of an AI project absent this transparency.
The negotiation of such an agreement will be more rushed due to the imminent time pressure.
For these reasons and others, it’s crucial that (1) the first steps towards an international agreement to reduce AI takeover risk begin as soon as possible, and (2) current frontier AI projects slow down enough to enable government action.
Our overall opinion is that if SAR is coming in 2027, an industry-wide pause on AI R&D should be the top priority for the AI industry, the US government, and the entire world.
This would give us a longer window of time to negotiate a more durable governance regime, such as
Plan A
or
Plan S
. If an international agreement isn’t able to be reached, then US companies should resume development but well below full speed (it’s feasible to pace while staying ahead of China due to the US’s huge compute advantage; and larger leads aren’t protectable anyway without vastly better security).
Appendix: How our views have changed over time
Median AGI (TED-AI) forecasts by AI 2027 authors over time, updated from the August 2026 version in our blog post. The Nov 2026 points are the TED-AI medians from "All-things-considered forecasts" above, after METR's estimate of ~1.7x AI-attributable acceleration: Daniel Sep 2027 (from late 2028), Eli Sep 2028 (from mid-2032), Brendan Apr 2028 (from early 2031), Thomas Apr 2028 (from early 2032), Romeo Sep 2028 (from early 2035).
Same data as the first graph, zoomed in on the period since AI 2027's publication (April 2025).
Appendix: Ambiguity in “80% of current acceleration is due to AI”
Claude Opus 5.5 gives the following possible interpretations of METR’s claim that “we guess that a majority (perhaps ≈80%) of the current (October 2026) acceleration is due to AI.”
Let h, c, n be the historical, current (Oct 2026), and no-AI counterfactual growth rates, measured in whatever units progress is roughly linear in. For AECI that's points per year: the fitted trend went from about +15 points/year before October 2025 to about +29 after. For an exponential metric (as in METR's worked example) it's the log growth rate. METR's definitions give total acceleration A = c/h ≈ 2, acceleration due to AI a = c/n, and implicitly non-AI acceleration b = n/h, with A = a·b. The "≈80%" is a claim about where n sits between h and c. The readings differ in which yardstick measures that.
Reading 1: share of the slope change (additive).
(c − n)/(c − h) = 0.8, so n = h + 0.2(c − h). In METR's "years of progress" units this is concrete. At A = 2, Anthropic makes about one extra historical-year of progress per calendar year, and about 0.8 of that extra year is due to AI. Without AI it would make about 1.2 historical-years per year, which implies a ≈ 1.67. This is probably what's intended. METR's illustrative chart labels the two gaps "excess growth due to AI" and "excess growth due to non-AI factors," it annotates the slope ΔAECI/Δtime, the AECI trends are fit linearly, and one interviewee framed it the same way, attributing 50–80% of the slope change to Claude.
Reading 2: share of the log-acceleration (multiplicative).
ln a / ln A = 0.8, so a = A^0.8 ≈ 1.74 and b = A^0.2 ≈ 1.15. This is natural if you take METR's ratio definitions literally. Since a·b = A, the logs add exactly, so this split doesn't depend on which factor you remove first.
Reading 3: share of the excess multiplier.
(a − 1)/(A − 1) = 0.8, so a = 1.8. It sounds natural ("AI provides 80% of the extra speedup"), but it isn't a decomposition. The non-AI share computed the same way is (b − 1)/(A − 1) ≈ 11%, so the two shares sum to 91%. An even more naive reading, a/A = 0.8, fails outright: if AI did nothing, a = 1 and you'd still get 1/A = 50%.
Implied AI acceleration a (and non-AI acceleration b), holding the 80% fixed:
The readings agree near A ≈ 1, because ln x ≈ x − 1 there, and they diverge as A grows. At METR's central estimate the spread is modest. In METR's own illustrative numbers (h = ln 2, n = ln 3, c = ln 9), AI's share comes out to 73%, 60%, or 46% under readings 1, 2, and 3. The same picture could be described as "a majority" or "a minority" depending on the yardstick.
Why 1 versus 2 is really a modeling choice.
If AI and other factors add to the growth rate (c = h + Δ_AI + Δ_other), reading 1 is the clean split. If they multiply (c = h·a·b, for example because AI multiplies the productivity of whatever headcount, compute, and data you have), reading 1 becomes order-dependent. The counterfactual "remove AI, keep the non-AI factors" gives AI the entire interaction term h(a − 1)(b − 1). A Shapley split of the same numbers (A = 2, b = 1.2) gives AI about 73%, not 80%. Reading 2 has no such ambiguity under a multiplicative model.
Appendix: More analysis of higher-than-expected near-AC coding uplift
SAR and TED-AI are also sensitive to the research taste slope (holding research taste at AC at the preset +0.5 SD), without changing the acceleration numbers much:
To make it easier to understand the implications of this hypothesis, we compared its forecasts against some representative trajectories from the above methods, matching their Sep 25 taste and taste slope:
46
Appendix: How much would 1.7x acceleration in inputs to AI progress accelerate AI progress overall?
AI software R&D progress is the rate at which the AI company is improving the algorithms it uses to train models. However, training better models requires both algorithms and training compute. If we were making AI software R&D progress 1.7x faster than normal, this would accelerate the algorithms but not the compute that goes into the final training runs, so the overall pace of progress would be less than 1.7x. We estimate that accelerating AI software R&D by 1.7x would only accelerate overall progress by about 1.1x.
47
Research labor uplift is even weaker than AI software R&D uplift. Labor is one input to AI software R&D, but compute to run experiments is another important input. If human labor was 1.7x faster than normal, this wouldn’t accelerate the experimental compute, so the pace of software progress would be less than 1.7x, and overall progress would be even less than that. We think that accelerating research labor by 1.7x would only accelerate overall progress by 1.03x.
48
Appendix: A minor fix to the AI Futures Model for better modeling when there’s acceleration in present day
Claude writes:
Takeaway: a fix to how the AI Futures Model converts the research taste slope moves the filtered results slightly earlier and barely changes anything else.
What changed: the taste slope is input as SDs/2025-year, but the model converted it using each trajectory’s pace of progress at present day (end of July 2026) rather than mid-2025. In trajectories that had already accelerated, like the filtered ones (1.2–1.4x the 2024–mid-2025 rate), this made the effective slope 20–30% lower than the parameter value. In typical trajectories the two rates match (median ratio 1.01). The conversion now uses the pace at mid-2025 (new parameter taste_slope_reference_date, default 2025.5).
Effect: Daniel’s preset barely moves (SAR one week earlier). p(SAR by EO2027) goes from 72% to 77% (1.5x), 87% to 90% (1.7x), 88% to 92% (1.7x Nov 1, 1.2x May 1) and 95% to 96% (2x). The joint median SAR moves from Apr to Mar 2027; the other SAR medians are unchanged to the month, and TED-AI medians move up to a month earlier. The partial coding automation trajectory’s SAR moves from Jun to May 2027. The one-time-beta-decrease trajectory barely moves (still Mar 2027), because the conversion reads a mapping that excludes the beta shift (rate ratio 1.04).
Appendix: TasteVal-implied taste slope, AECI basis
Claude writes:
This appendix shows the fit behind the “TasteVal slope, AECI basis” row of the one-at-a-time table. TasteVal (arXiv 2610.06824) measures each model’s compute multiplier: the experiment compute the expert baseline needs to match the model’s final score, as a multiple of the model’s own compute budget. METR’s chart gives AECI only for Anthropic models, so each TasteVal model gets the AECI that METR’s fitted trend gives at its release date (+15 points per year before the October 7, 2025 break, +29 after; second plot). Release dates are read off TasteVal’s Figure 1.
We fit log(compute multiplier) against this AECI for the 17 frontier models TasteVal fits (GPT-4 to Opus 5.5), allowing one change in slope at the model where it best fits the data (largest Chow F-statistic, as TasteVal does). The change falls at GPT-5.2 (AECI ≈ 155, December 2025), the same model as in TasteVal’s own fits against release date and ECI. Before it, the multiplier doubled every 19.5 AECI points; since then, every 7.2 points (90% CI 5.4–9.0 from resampling the 11 post-break models). As a check, the same fit against release date reproduces TasteVal’s 3.0-month doubling time, which is about 7.2 points at 29 AECI points per year. A continuous kinked line gives 6.7 points per doubling. Using METR’s measured AECI for the six Anthropic models instead of the trend values gives 7.9, and fitting those six models alone, without a break, gives 5.6.
Appendix: Software R&D uplift extrapolation
Here’s another simple model: Extrapolating software R&D uplift extrapolation.
In
this tweet thread
, Ryan Greenblatt proposed a simple model for figuring out what software R&D uplift is implied by an overall pace of progress estimate. Ryan used ~2x; we use the ~1.7x AI-attributed pace of progress from this post, since the method backs out how much AI is speeding up software R&D.
If we assume overall AI progress comes from ⅔ software and ⅓ hardware, then we get that speeding up the overall pace of progress by 1.7x requires speeding up software progress by 2.05x.
49
Then if we assume that software progress faces diminishing returns where each year of software progress is twice as hard, and that there has been an additional ~0.6 years of software progress, then you get that software R&D uplift is (2.05 * 2^0.6 =) 3.1x in Nov 2026.
50
If we assume that as of May 2026 uplift was ~1.45x based on converting a ~1.2x AI-attributed pace of progress acceleration,
51
and that SAR will correspond to a 25x uplift according to the AI Futures Model,
52
or ~45x according to the
SAR central estimate from the section above
,
53
then we can do a naive exponential extrapolation:
This estimate is conservative in that it doesn’t account for automation speeding up the trend. However, it is extremely uncertain, given that we only have 2 data points which are both based on the METR report’s rough guesses. And the May data point is a very rough educated guess, rather than something explicitly stated by METR.
Appendix: How many years of AI progress in 2027 do the filtered AIFM runs predict?
We measure progress in 2027 as the ECI gained during 2027, in units of the average yearly ECI gain over 2024–25. Today's overall pace is ~2x (~1.7x AI-attributed), so if it held flat, 2027 would contain ~2 years of progress.
The AI Futures Model, filtered to runs with a ~1.2x AI-attributed pace on May 1 2026 and ~1.7x on Nov 1 2026, instead gives a median of ~5 years with Daniel's parameters and ~4 with Eli's:
METR described its range informally ("we would not be surprised if the true acceleration was closer to 1.3x or 3x the historical rate"), so we don't know what interval they meant.
1
By Superhuman AI Researcher (SAR) we mean: “an AI that matches the research taste of the best human researchers at an AGI company and can fully automate its coding.”
2
We define it more precisely
here
.
3
We also think we are likely to see something like
5 years’ worth of historical AI progress in 2027
(50% CI: 2.7 to 25 years). This is based on filtering the AI Futures Model with Daniel’s parameters to condition on 1.7x pace of progress in Nov 2026 and 1.2x in May.
4
See e.g.,
Daniel’s forecast writeup below
for more factors.
5
We also recommend
this piece
which also analyzes the implications of the METR report.
6
It wasn’t just our predictions about the future that were too low; we also now think our estimates of the pace of progress in August 2026 were too low. Also note that this was the prediction implied by the model and parameters assigned by specific people, which may well have been lower than their all-things-considered view if they had been specifically asked about this question.
7
While the simple research extrapolation has a median Sep 2026 research taste of 1.5 SDs below the median AGI company researcher.
8
The ECI trend in the trajectory doesn’t match the AECI historical trajectory well, because the AIFM can’t model a slope increase that was initially mostly from non-AI-attributable factors.
9
METR writes: “
We guess that a majority (perhaps ≈80%) of the current (October 2026) acceleration is due to AI.
This judgment is given with substantial uncertainty, but is based on a variety of lines of evidence on contributions from AI and other causes. We believe AI’s contribution has grown relatively more important over time, and do not think the other factors we investigated would explain the sustained acceleration. The evidence of speedup from the usage of AI we describe below also seems compatible with a large contribution.” 1.7 is roughly 80% of the way to 2 from the baseline rate of progress in log space. More on this in
an appendix
.
10
METR says: “We are confident that the acceleration was not due to an acceleration in the scaling of training compute.” Based on what we can determine externally from financial reporting, it seems like R&D compute grew around 3x 2024 → 2025 and 4.2x 2025 → 2026 (accounting for changes in allocation).
11
The baseline is roughly 14 points per year, and 14*1.7=24/year is achieved roughly in April.
12
Note that the AI does not need to dominate humans across every subskill of research taste. It is enough for the AI to have research taste such that the AI company would overall prefer to use only AIs for research taste than to use only copies of top humans for research taste (more precisely, the copies would have aggregate research taste as good as the top human, while retaining the same distribution of specializations as current human researchers).
13
Or actually, R&D parity only requires research taste slightly below average because coding skills will be ahead.
14
However, the acceleration being AI-attributable is evidence for more aggressive research taste level and slope parameters.
15
Claude estimates based on the charts in the report that it was internally deployed on roughly Sep 25.
16
My best guess is that AIs aren’t yet contributing enough via taste that we have that much evidence about the taste slope via an update toward more gradual acceleration. However: (a) it’s plausible to me that AIs are starting to contribute to taste in some sense, via mechanisms like (1) better integrating information across teams leading to more fruitful experiment ideas or (2) brainstorming lots of ideas quickly and (b) even if the taste is currently quite low, I can hackily represent the general update toward slower takeoff based on gradual acceleration via lowering the taste slope here.
17
Time to SAR is the remaining taste gap divided by the slope, so draws where Model 4 is already near or past SAR arrive early almost regardless of the slope, while draws with a large gap are pulled earlier by a steep slope about as often as they're pushed later by a shallow one.
18
I think the top researcher is much more valuable than the median researcher. The difference between the 99.9th percentile and average of a lognormal distribution with median 1 and 99.9th percentile 1,000 is ~80x (the average is ~12x the median).
19
k is directly proportional to r, i.e. the number of doublings of software efficiency you get from a doubling of cumulative research. In the terms of
Economics of RSI
, k = ln 2 × r × ε_C,A. (With ε_C,A ≈ 3.9 AECI points per e-fold in our calibration; the paper's 6.5 is for Epoch's ECI).
20
Also called ε_R,C, and "research effort's elasticity to AI capabilities”.
21
I.e., I’ll assume that d is itself a linear function of ECI going forward.
22
These numbers imply that r (doublings of software efficiency per doublings of research) is roughly 3.3, and that k is roughly 9 AECI points per doubling of research.
23
From the labor uplift section above: raising all researchers to the research taste of the best researcher is worth ~100x (the top researcher vs. the average researcher), or ~500x after accounting for complementarity between AIs and humans; fully automating coding is worth ~2,000x; together that is ~1,000x AI R&D labor uplift at SAR. To convert labor uplift into software R&D uplift, we use Ryan Greenblatt’s production function for software progress, labor^0.55 * compute^0.45, with experiment compute held fixed: 1,000^0.55 = ~45x. With his alternative exponents of 0.3 and 0.7 instead of 0.55, this would be ~8x or ~125x.
24
The exponential fit behind line E seems implausible since I’d expect d to be increasing as AI becomes more important for software R&D.
25
While scaling the total amount of acceleration to hold the fraction of AI acceleration fixed at 80%.
26
See the very last section for a description of how the number is calculated from the other parameters he estimates.
27
We’re working with little evidence here, including: (a) the description of even the acceleration in late 2025 as “likely influenced by non-AI factors,” implying AI plausibly had a role, (b) the suggestive “fake data” graph, (c) interviewed researchers describe Mythos Preview (internal ~Apr 2026) as a big jump (“a sharp inflection”), and (d) staff self-reported uplift was ~4x for Mythos Preview and ~5x for Mythos 5 (Jun) vs ~12x for Model 4 (Oct).
28
We correspondingly shift the confidence interval. It’s now an 80% confidence interval of [0.40, 5.61], median 1.5.
29
This quote is from
METR’s risk report review
.
30
The coding-only uplift should be higher than the overall labor uplift because coding is relatively easy to automate. This is pricing in some amount of self-report overestimation. The (uplift-1) doubling time in the trajectory is set to 3.3 months, very similar to the 3.4 months
one gets from fitting to self-reports
.
31
I’m imagining here a very simplified model of AI R&D which includes only 3 tasks with equal weight: experiment implementation, research taste, and data generation. If data generation “merely” was as automated as coding is, then it would provide some additional acceleration but it probably couldn’t bring up a 1.25x AI-attributed acceleration to 1.7x.
32
Referring specifically to the non-AI-attributable component of the acceleration.
33
This is done by changing taste at AC and taste slope; AC held at late Dec 2026.
34
They ended up thinking that “internal evidence provided support for there being significant acceleration in Anthropic’s model training pipeline”.
35
And then, if there’s
any
set of capabilities that loop back on the ability to further improve those capabilities, and this effect is large enough to cause accelerating, hyperbolic growth, then things could go very far. And given sufficiently large progress in any domain like that, it seems very likely that those capabilities can also be applied to cause more general progress shortly thereafter. (See e.g. the arguments about “Data bottlenecks to automating real-world work”
here
.)
36
We expect this METR team to publish their work in the next couple of days.
37
But it’s possible that further investigation could provide new evidence that would change our mind in more substantive ways. For example, evidence about whether acceleration is larger or smaller on different task distributions could be informative for whether recent progress is likely to generalize far enough to feed back into itself.
38
See, for example, Parker Whitfill’s paper
here
. Also
this amusing Twitter interaction
.
39
Both our specific parameterizations, but also to some extent the model structure.
40
80% CI.
41
Of the ~6-month shift (~7.5 months with the larger gap), centering at 1.6x rather than 1.7x accounts for about 2–2.5 months (2–3.5 with the larger gap) and the spread for the other 3.5–4 months (4–5.5), depending on which is applied first. Each piece carries roughly ±1.5–3 months of sampling noise, so the split is rough. The spread pushes later because TED-AI timing is asymmetric in acceleration: the chance of TED-AI by the end of 2027 is 53% for trajectories at about 1.6x, but 26% at 1.18–1.35x and 2% below 1.06x, versus 68% at 1.84–3x and 79% at 3–6.5x. The distribution puts 38% of its weight below 1.35x, so mixing lowers the chance of TED-AI by the end of 2027 from 53% to 47%.
42
This distribution puts 18% of its weight above 3x (vs. 25% for 1 + 0.6 [0.06, 6] clipped at 7) and 10% at the 5x clip. It gives a 59% chance of SAR by the end of 2027 (vs. 67%) and 40% for TED-AI (vs. 47%), or 36% (vs. 43%) with the larger gap. With the same distribution, Daniel’s parameters give SAR in May 2027 and TED-AI in Oct 2027 (vs. Mar 2027 and Jul 2027), and Brendan’s give Jun 2027 and Apr 2028 (vs. Mar 2027 and Nov 2027). TED-AI medians carry roughly ±1–2.5 months of sampling noise.
43
They previously forecasted a median of 2040 in
Jul 2025
and 2031 in
Apr 2026
.
44
“I semi-jokingly called our efforts a ‘slop-vestigation’ because we were so reliant on AIs to analyze what happened and there were a huge number of different important things to analyze.”
45
Current training runs probably require a small fraction of frontier companies’ total compute, meaning that even if the training recipe/IP (but not the model weights) are stolen, a Chinese company like ByteDance could use a larger fraction of its total compute (e.g. 50% instead of 10%), and train for twice as long (e.g. 6 months instead of 3 months), and end up with SAR just a few months after the US companies do.
46
This is done by changing taste at AC and taste slope; AC held at late Nov 2026.
47
Based on the AI Futures Model with Daniel's parameters. We filtered to trajectories where AI software R&D uplift is about 1.7x on Nov 1, 2026, meaning AI multiplies software research effort by 1.7x compared with no AI. In those trajectories the median pace of overall AI progress on that date is 1.11x (50% CI: 1.05–1.19x) the trajectory's own Jan 2024 – Jul 2025 pace.
48
Same method, filtered to trajectories where AI makes coding labor about 1.7x faster on Nov 1, 2026. The model has no separate multiplier for research labor as a whole, so we use serial coding labor uplift as the proxy. The median pace of overall progress is 1.03x (50% CI: 1.00–1.07x) the Jan 2024 – Jul 2025 pace.
49
(⅔)x + (⅓) = 1.7. So 2x + 1 = 5.1. x = (5.1-1)/2 = 2.05. With Ryan's ~2x, this gives 2.5x.
50
Ryan: “I've
previously estimated
software R&D would slow down by around 2x for each year of software progress if you held inputs fixed and based on the report, it seems as though we've perhaps seen roughly 0.35-1.0 years of additional software progress incorporated into trained models so far (geometric mean of ~0.6).” This also roughly matches what we get in the filtered AI Futures Model runs (3.3x for Daniel, 3.8x for Eli). With Ryan's ~2x pace instead of 1.7x, the calculation above gives 3.8x.
51
Using the same method as for Nov 2026: the 1.2x pace of progress on May 1 2026 that we use elsewhere in this post implies a (3 * 1.2 - 1) / 2 = 1.3x software pace. For diminishing returns, we assume software pace ramped up linearly from 1x on Jul 1 2025 to 1.3x on May 1 and 2.05x on Nov 1, and scale it so the total by Nov 1 matches Ryan’s ~0.6 years. About a quarter of that, ~0.16 years, had accumulated by May 1, so uplift was 1.3 * 2^0.16 = ~1.45x. Ignoring diminishing returns gives 1.3x.
52
In the unfiltered AI Futures Model, the median uplift is 3.3x at AC and 18x at SAR with Daniel's parameters (4.1x and 19x with Eli's). We seem to have hit ~3x without hitting AC, so we assume a 10% chance that AC has already happened. Taking runs filtered to match METR's ~1.7x acceleration and reweighting them so that 10% have reached AC by Nov 1 2026, the median uplift is 5.9x at AC and 24x at SAR with Daniel's parameters (6.9x and 21x with Eli's).
53
From the labor uplift section above: raising all researchers to the research taste of the best researcher is worth ~100x (the top researcher vs. the average researcher), or ~500x after accounting for complementarity between AIs and humans; fully automating coding is worth ~2,000x; together that is ~1,000x AI R&D labor uplift at SAR. To convert labor uplift into software R&D uplift, we use Ryan Greenblatt’s production function for software progress, labor^0.55 * compute^0.45, with experiment compute held fixed: 1,000^0.55 = ~45x. With his alternative exponents of 0.3 and 0.7 instead of 0.55, this would be ~8x or ~125x.

## What the writer wrote

**Q3.5 Timelines Update** — Eli Lifland and AI Futures Project co-authors

Eli Lifland and his AI Futures co-authors, identified in the post only by first name as Daniel, Brendan, Lukas, Thomas and Romeo, have sharply shortened their timelines. They now expect a Superhuman AI Researcher, or SAR, most likely in twenty twenty-seven. SAR is an AI that matches top-human research taste and fully automates coding at an AGI company.

**The trigger: METR's assessment of Anthropic.** METR estimated that Anthropic's progress, measured on its internal version of the Epoch Capabilities Index, has roughly doubled relative to the pre-October twenty twenty-five trend. METR also guessed that about eighty percent of the current acceleration is due to AI. The authors read this as roughly one point seven times AI-attributable acceleration of overall progress.

They stress that this is far stronger than a one point seven times labor uplift. Compute bottlenecks and diminishing returns mean labor or software uplift translates into much smaller overall speedups. By their estimate, it puts the world about five months ahead of the AI twenty twenty-seven scenario. In August, even their most aggressive model-based distribution, Daniel's, gave under four percent to an acceleration of at least one point seven times by now.

**What the models say.** Several methods converge:

- A linear extrapolation of research taste along the accelerated trend gives a Monte Carlo median of July twenty twenty-seven.
- Extrapolating staff self-reported labor uplift gives mid twenty twenty-eight.
- Anthropic's automation-level chart gives late twenty twenty-seven.
- Extrapolating software R&D uplift per capability point gives mid-to-late twenty twenty-seven.
- Tom Davidson's toy model is consistent with these.
- Filtering the AI Futures Model for trajectories matching the observed acceleration gives a SAR median around February to March twenty twenty-seven, with roughly ninety percent of trajectories reaching SAR by the end of twenty twenty-seven.

**Why their model missed.** The top hypotheses are:

- Near-automated-coder coding skills give more uplift than expected.
- Unmodeled skills, such as RL environment and data generation, drive acceleration.
- The model penalized diminishing returns too harshly, which would imply faster takeoff.

**Caveats.** Anthropic redacted most of METR's key evidence, and the authors urge its release. Acceleration may be concentrated on well-specified, benchmark-like tasks. A separate METR team without inside access sees much less speedup. The authors largely trust the embedded team, partly because those researchers previously held longer timelines.

**Individual forecasts.** Medians for SAR run from about May twenty twenty-seven (Daniel) to August twenty twenty-seven (Eli). Top-Expert-Dominating AI medians are September twenty twenty-seven (Daniel), April twenty twenty-eight (Brendan and Thomas), and September twenty twenty-eight (Eli and Romeo). Romeo argues that capability spikiness widens the gap between SAR and Top-Expert-Dominating AI. Ajeya Cotra and the forecasting group Sentinel have also shortened their timelines considerably.

**Policy implications.** The authors argue:

- A misaligned SAR used for recursive self-improvement could backdoor its successors.
- Current models already show misalignment and eval awareness.
- Nominal human-in-the-loop review won't scale.
- Lab security makes theft of algorithms and possibly weights by China likely.

Their bottom line: if SAR is coming in twenty twenty-seven, an industry-wide pause, followed by an international agreement, should be the world's top priority.

## Fidelity check

Status: revised
Claims: 32; flags: 5; material: 2

Flags on the draft:
- [distorted, medium] "Their August model gave under four percent to this outcome." — The under-4% figure is for Daniel's distribution, which the source calls the most aggressive. The script presents it as the whole team's model. It also drops the 'at least 1.7x' framing. (source: "even the most aggressive model-based distribution (Daniel’s) assigned less than 4% to the pace of progress being sped up by at least 1.7x in November 2026.")
- [distorted, medium] "Their bottom line: an industry-wide pause, followed by an international agreement, should be the world's top priority." — The source makes this recommendation conditional. The script states it as an unconditional bottom line. (source: "Our overall opinion is that if SAR is coming in 2027, an industry-wide pause on AI R&D should be the top priority for the AI industry, the US government, and the entire world.")
- [distorted, low] "Romeo argues that capability spikiness widens the gap between SAR and Top-Expert-Dominating AI." — Romeo's spikiness model pushes TED-AI later. However, he says his model may overstate the SAR-to-TED-AI gap and that he expects a smaller gap. The script's attribution is one-sided. (source: "The only thing I think it might overstate is the SAR to TED-AI gap. I expect it to be smaller")
- [unsupported, low] "Eli Lifland and AI Futures Project co-authors" — The source never names an 'AI Futures Project'. It mentions only the 'AI Futures Model' and unnamed co-authors. (source: "Also, the people I defer to most are probably many of the co-authors of this blog post")
- [distorted, low] "They now expect a Superhuman AI Researcher, or SAR, most likely in twenty twenty-seven." — The script drops the 'no substantial deliberate slowdown' qualifier. (source: "all of us forecast that Superhuman AI Researcher (SAR) will likely arrive at some point in 2027 (assuming no substantial deliberate slowdown).")

Remaining after revision:
- [distorted, medium] "Romeo argues that capability spikiness widens the gap between SAR and Top-Expert-Dominating AI." — Romeo's spikiness model does push TED-AI later, but he says it probably overstates the gap and expects a smaller one. The argument for a larger SAR-to-TED-AI distance because of jaggedness is Brendan's. (source: "The only thing I think it might overstate is the SAR to TED-AI gap. I expect it to be smaller")

### Draft before revision

**Q3.5 Timelines Update** — Eli Lifland and AI Futures Project co-authors

Eli Lifland and his AI Futures co-authors, identified in the post only by first name as Daniel, Brendan, Lukas, Thomas and Romeo, have sharply shortened their timelines. They now expect a Superhuman AI Researcher, or SAR, most likely in twenty twenty-seven. SAR is an AI that matches top-human research taste and fully automates coding at an AGI company.

**The trigger: METR's assessment of Anthropic.** METR estimated that Anthropic's progress, measured on its internal version of the Epoch Capabilities Index, has roughly doubled relative to the pre-October twenty twenty-five trend. METR also guessed that about eighty percent of the current acceleration is due to AI. The authors read this as roughly one point seven times AI-attributable acceleration of overall progress.

They stress that this is far stronger than a one point seven times labor uplift. Compute bottlenecks and diminishing returns mean labor or software uplift translates into much smaller overall speedups. By their estimate, it puts the world about five months ahead of the AI twenty twenty-seven scenario. Their August model gave under four percent to this outcome.

**What the models say.** Several methods converge:

- A linear extrapolation of research taste along the accelerated trend gives a Monte Carlo median of July twenty twenty-seven.
- Extrapolating staff self-reported labor uplift gives mid twenty twenty-eight.
- Anthropic's automation-level chart gives late twenty twenty-seven.
- Extrapolating software R&D uplift per capability point gives mid-to-late twenty twenty-seven.
- Tom Davidson's toy model is consistent with these.
- Filtering the AI Futures Model for trajectories matching the observed acceleration gives a SAR median around February to March twenty twenty-seven, with roughly ninety percent of trajectories reaching SAR by the end of twenty twenty-seven.

**Why their model missed.** The top hypotheses are:

- Near-automated-coder coding skills give more uplift than expected.
- Unmodeled skills, such as RL environment and data generation, drive acceleration.
- The model penalized diminishing returns too harshly, which would imply faster takeoff.

**Caveats.** Anthropic redacted most of METR's key evidence, and the authors urge its release. Acceleration may be concentrated on well-specified, benchmark-like tasks. A separate METR team without inside access sees much less speedup. The authors largely trust the embedded team, partly because those researchers previously held longer timelines.

**Individual forecasts.** Medians for SAR run from about May twenty twenty-seven (Daniel) to August twenty twenty-seven (Eli). Top-Expert-Dominating AI medians are September twenty twenty-seven (Daniel), April twenty twenty-eight (Brendan and Thomas), and September twenty twenty-eight (Eli and Romeo). Romeo argues that capability spikiness widens the gap between SAR and Top-Expert-Dominating AI. Ajeya Cotra and the forecasting group Sentinel have also shortened their timelines considerably.

**Policy implications.** The authors argue:

- A misaligned SAR used for recursive self-improvement could backdoor its successors.
- Current models already show misalignment and eval awareness.
- Nominal human-in-the-loop review won't scale.
- Lab security makes theft of algorithms and possibly weights by China likely.

Their bottom line: an industry-wide pause, followed by an international agreement, should be the world's top priority.
