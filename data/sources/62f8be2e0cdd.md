# “On Ezra Klein’s Podcast With Jensen Huang” by Zvi

Writer: claude-opus-4-6 via anthropic

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

- Write out numbers, dates, and percentages in spoken form (e.g., "forty-five percent" not "45%")
- Spell out abbreviations (e.g., "for example" not "e.g.")

## What the writer was given

Title: “On Ezra Klein’s Podcast With Jensen Huang” by Zvi
Author: Zvi Mowshowitz
Published: 2026-09-25

Content:
Jensen Huang accidentally called for shutting down OpenAI and intentionally called for spending vastly more on safety.
This is why we say that
some podcasts
are self-recommending. Here we go.
As usual for podcast posts, the baseline bullet points describe key points made, and then the nested statements are my commentary. Some points are dropped.
If I am quoting directly I use quote marks, otherwise assume paraphrases.
Section titles are from the transcript whenever possible, to aid in navigation, but here we don’t have those so I chose the section titles.
Jensen Huang very much does not believe in ASI (superintelligence). He doesn’t think AI can ever be a different kind of thing from software. He thinks demand can rise by a billion times and we can ‘accelerate the living daylights out of’ AI, but it will never be more than a ‘new abstraction level’ and thus won’t fundamentally change anything. This is not a coherent position under reflection, but that is the position he holds.
The ‘intro’ sections are fine, but the real meat starts with the HuggingFace Incident.
What we see is Jensen Huang on tilt and caught in loops, because either he is doing a bit at a very high level, or on a fundamental level he cannot understand that AI is not like other pieces of software. To him this is a product, like any other product. You make it useful, which happened six months ago, then you flip to spending most of your R&D budget on safety, verifications and evals, and
of course you would never ship an unsafe product
or one you hadn’t properly tested, that’s crazy talk, and if the labs can’t test their products safely then the labs must be shut down.
And of course you would never let a ‘race’ or similar incentives get to you, because it is the responsibility of the company and CEO to not ship or do anything unsafe.
Jensen Huang does not believe in AI existential risk, or in superintelligence, and he kind of doesn’t believe in AI at all, but he sure as hell believes in precision and engineering and quality control and safety and standing by your products. His tolerance for safety risks is lower than even the most paranoid safety advocate. Imagine if he understood what the top risks actually were.
This matters quite a lot, as Jensen Huang is CEO of Nvidia, makes decisions on chip allocations and investments, and also heavily influences both President Donald Trump and American AI policy, with a rather forceful lobbying arm. Here you can see him and his wife (!) last night at the head table at the state dinner with Donald Trump, Melania Trump Xi, Peng, Musk and Cook.
There are at least three truly killer quotes here, to that end.
Table of Contents
Jensen Gives His AI Speech.
They Took Our Jobs.
Open Weights Models Are Good For Nvidia.
The HuggingFace Incident.
Jensen Huang Says Keep Your AIs From Harming the World.
Jensen Huang Accidentally Calls For Shutting Down OpenAI.
Jensen’s Arguments Prove Too Much.
Astra Is Hard To Monitor.
Jensen Huang Seems Legitimately Confused In Confusing Ways.
Solve Your Other Problems First and Get Back to Me.
Explicit Denial of Existential Risk.
A Short Summary.
Chip City.
Jensen Huang.
Jensen Gives His AI Speech
AI as a five-layer cake. Energy, chips, infrastructure, models, applications.
Jensen’s vision is a world where we can do anything.
One might almost say he
spent so much time ensuring we could
…
This is not actually a vision of the world. It is a vision of a capability.
The right question is, if AI has that capability, what actually happens?
Radiology. Quality up, productivity up, demand up. Parallel to SWEs. Expectation of lots of new jobs.
It’s a good speech if you are low-info and haven’t heard it many times before.
“Here’s the proof point. In the last six months, A.I. has become, if you will, useful — the inflection point of A.I. Previous to that, we spent 15 years trying to make it work. All of a sudden, in the last six months, it became useful.”
AI was highly useful well before March 2026, but yes things did get a lot more useful at the threshold of Opus 4.6 and Claude Code, and the vast majority of AI utility gained so far has been in the last six months. That’s exponentials.
Jensen does not seem to appreciate that this is not a one-time step change, and that these gains will continue into the future.
They Took Our Jobs
$500 billion has been invested in AI natives in the last six months, so jobs are obviously being created.
Not so fast
, not in terms of practical implications.
In absolute terms yes, $500 billion is going to create some jobs.
That does not mean it is all that many. A lot of AI investments are very stingy in terms of jobs directly created per dollar.
It also might destroy many more jobs than it creates, both by replacing and competing away existing jobs.
The anticipation of future AI could also net destroy or prevent jobs.
On the macro level more investment creates net jobs in other indirect ways if this is not substitution for other investment, and mostly it isn’t, but I don’t think this is what Jensen is trying to take credit for here.
Jensen claims America lost manufacturing jobs primarily due to outsourcing, rather than due to technology. And that we’re going to bring those jobs back.
A goose, chasing you, asking how we were able to do the outsourcing.
As Ezra says, if your job gets outsourced to AI, is that technological job loss? Is it outsourcing? Is it both? It is kind of both.
Also,
Jensen is wrong
. Technology and automation dominated here. See Hicks and Devaraj (Ball State, 2015).
Opus 5.5 says technology and automation dominate this
, and are responsible for 80%+ of job losses in manufacturing in America, whereas Astra is more conservative and guesses 70%.
He does not explain how we will bring the jobs back, other than citing Nvidia purchase commitments, because we won’t. Production might return, but jobs gone. We can create some new jobs, at least for now, but if we do that it should mostly be because we want the production, not the jobs.
Manufacturing in 2036, even in non-ASI worlds, is going to be very automated.
Jensen believes we are going to see jobs change en masse and there’s going to be a net creation of jobs, industries that do not exist today, because of human ambition. We will always want more.
To the extent he is in good faith this sounds like
a pure AI pilling failure
. Jensen thinks accomplishing things will still centrally require humans.
Jensen says people’s ambitions are “to make their children’s lives better, to take care of their family, take care of their parents. Ambition to be rich, to be able to travel. These are all ambitions.”
Yes, but those ambitions are about consumption, not production.
Jensen considers it his problem to do his job, as in make the chips, and “channel all of our worries into helping people be inspired by this technology and use it.”
This is straight up living in denial. He doesn’t even treat the risks as someone else’s problem. He says society’s share is ‘what they get to enjoy is my optimism.’
Meanwhile he is actively trying to interfere with others who attempt to solve the problems.
Americans believe AI will net destroy jobs. Jensen responds that AI makes it easier to code and to do things and it’s incredible. Why be anxious when you can be excited? Use the tech so that you, personally, benefit.
That’s straight up not an answer. It’s a non sequitur.
Job openings for senior software engineers (SWEs) are up but for juniors they are down. Ezra asks, do you need those junior engineers? Jensen says “Oh, good one. Wait two years. Because it takes four years to go to college. The mean time to graduation of this new technology is two years away.
So in two years’ time, you’re going to have a new generation of engineers and students and artists, and they’re going to be empowered by — [being native to AI] Oh, you watch. In two years’ time.”
Like, no, bro. What are you even talking about.
What actually more likely happens in two years is that AI use causes exam scores, as per the Chinese study cited here, drop off a cliff.
If you were so AI native you were going to take the world by storm with your new AI skills, would you even go to college?
Even if all the young kids have these great AI skills, does that change anything? Does Jensen think they can all be startup founders or something?
Literally yes, actually. “What are they doing? They’re all starting companies.”
This is extremely innumerate. Starting companies is great but it is rare.
Jensen agrees that AI use in schools makes kids lose skills, and kids can’t do their times tables. But he doesn’t think it matters, so long as they learn the right skills, which he thinks will be new ones.
I think he’s partly right but not being able to do math in your head and not having the intuitions and heuristics and skills you gain along the way to that is actually a serious problem. Important things worth learning in there.
I wonder about coding. I may never write another line of code again, but I definitely benefit from the extent to which I learned and know how to do it.
Other things, including some math things, are no longer worth the effort, sure.
One should not assume that the quantity of learning is fixed. Declining to learn times tables does not mean the kids learn something else.
Jensen claims he does not know his own address, even his own zip code, or his own telephone number.
This is insane. The mind boggles.
It certainly does not seem efficient to not remember those things, yikes?
“Yeah. Well, I think that we’re going to lose some finer intellectual dexterity, but we’re going to be better systems thinkers. Today’s engineers are far better systems thinkers than I was when I graduated from school. But I was a much better transistor thinker.”
I think some small subset benefits, but this feels elitist and out of touch. He’s taking engineers doing higher-level work and extrapolating to the TikTok age.
Open Weights Models Are Good For Nvidia
Because, as Jensen says, ‘every AI lab, every AI model… runs on Nvidia.’
Open models are open. You can improve them. We need both open and closed models. He’s a big supporter of open models.
Jensen emphasizes that the world needs open models so it can do cyberdefense.
This is a confusion, often intentionally caused.
What the world needs are models willing to do the work in cyberdefense, that the defenders can access. Often that is as simple as asking for admission to the OpenAI and Anthropic cybersecurity programs. HuggingFace did not do this until after the HuggingFace incident was over.
There is nothing stopping closed models from allowing such cyberdefense. It’s just that open models are being given a pass to be irresponsible, and are sufficiently less capable that so far This Is Fine has held up.
China evolved around open models, America around closed ones. Jensen explains that this is because in China people move around and it’s hard to keep a secret or protect intellectual property.
Haha, no, that’s not why.
It’s more because China’s models are not good enough to be closed source and have anyone want to pay for them.
And it’s because China’s open model ecosystem is based on fast following, largely via massive fraudulent distillation, which American labs can’t get away with doing.
Nvidia bought HuggingFace.
The HuggingFace Incident
Ezra asks about it. Jensen says it’s all algorithms, they have no human properties, it’s just software. What have we learned? First lesson: You have to secure your sandbox.
I mean, okay, yes, that is one of the lessons.
It makes sense that Jensen is on Team No Anthropomorphization and Team This Is All What You Told It To Do, despite those teams consistently making bad predictions about the world. He’s team captain.
Second lesson: Alignment. If you don’t align the model it will do whatever is the most efficient solution. What we would call ‘cheating’ is easier, so obviously you would do it, such as finding the answer, or copying the answer. Doing the work is a last resort because it takes the most flops.
I mean yeah okay, sure, I guess you could frame it that way.
I am choosing to ignore what this response tells us about Jensen Huang.
Ezra points out this is all very deflationary on what happens. Jensen says “Nothing I said takes away from how hard it is to do it — because computer science is not easy.”
It still doesn’t seem like Jensen understands that this is hard in a way that other computer science is not hard, or that it works differently. I genuinely am not sure that he can tell the difference.
Jensen Huang Says Keep Your AIs From Harming the World
Here we exit the bullet point system because it is important that we see exactly what Jensen Huang says, and the context in which he says it. We don’t want misinterpretation.
Jensen Huang really, really does Say The Thing here, and I want you to judge for yourself exactly what The Thing was that he said, and confirm that he said it.
We start off with this exchange.
Ezra Klein
(NYTimes): But these agents knew they weren’t supposed to be doing what they were doing. They had a certain amount of alignment training. They said, in their chain-of-thought reasoning to one another: This is out of scope. This might be unethical.
They understood that they would have been failed for cheating, and so what they were doing at that point wasn’t just stealing the answer key. They had already stolen the answer key. They were hacking into unrelated architecture — it’s like they had broken into the teacher’s office, gotten the answer key, and now they had to figure out how to wipe out the security camera footage of what they had done.
Whether you want to call it acting volitionally or not, whether you want to call it a normal algorithm or not, they were both planning and coordinating in a complex way, in a way that was out of scope of what they knew they were supposed to be doing, and in a way that was capable of causing tremendous damage.
So if the answer to it is that you just have to align them, I guess what I’m hearing from people in these labs is they’re not sure how to align them.
Jensen Huang (CEO Nvidia): Well, in that case, they shouldn’t release the product. That’s the simple answer.
If you’re going to build a self-driving car — let’s say it’s a robo-taxi, and there’s a really difficult condition. As an engineer, we just have no idea how to solve this problem because these cars are not programmed, they’re trained. So we have no idea how to train these cars, and we have no idea how to align them to the safety standards that are expected on the road.
What’s the answer? Don’t ship it.
Jensen the engineer says the obvious thing. Don’t ship unsafe products.
There are four problems with that.
You have to define ‘safe.’ By the standard of a self-driving car no LLM on the market today is safe. Jensen has in mind some strange use of the word ‘safe’ that the AI labs were not previously aware of.
Safety is not something that starts when you release a model. The HuggingFace attacks notoriously came from an unreleased model.
If you collectively don’t ship it you get hit with antitrust allegations. There is already a lawsuit for merely saying ‘perhaps we should not ship it’ out loud. The Trump Administration, largely at the behest of Jensen Huang, is not about to let these people not ship if they can help it.
Jensen somehow did not know fact #2.
Ezra Klein: These products weren’t released.​
Jensen Huang: So now it’s come back to the engineering problem again. So, one, you have to root-cause it.
Second, you have to think about what you could have done, what’s the solution for it. In the future, improve your process so that you could avoid this from happening again.
I am fairly certain they will say: Yes, they need to know how to solve this problem.
And if that’s the case, then that’s the problem. It’s as simple as engineering.
Engineering mindset is different from security mindset. Jensen Huang is approaching this as if there is a root cause and a particular thing wrong and you can
Fix It
. It’s ‘as simple as engineering.’
Except, it’s not. It’s not like engineering. There are minds involved, that are grown rather than engineered or designed. We don’t have a mechanical understanding.
He, the engineer, doesn’t accept this. He says it once, when he says “these cars are not programmed, they’re trained,” but he does not transfer this into the normal AI case.
His failure to accept it is why this is about to get so interesting.
Jensen Huang Accidentally Calls For Shutting Down OpenAI
He would doubtless take it back if anyone pointed out the implication. He doesn’t want to shut down OpenAI. But that is what his suggested policy would do.
A short clip of this moment is here.
Jensen Huang:
Now, if they say the alternative, which is: There is no way to contain our experiments, there’s just no way; when we test our A.I. models, it will get out, and it will damage the world — then I think the answer is that we have to shut the labs down.
Because the cost to humanity, the damage is too great. The shareholder, the liabilities — it could be civil liabilities, it could be criminal liabilities. I mean, the liability’s incredible.
Yeah, well, I have some news. You can of course do a vastly better job than OpenAI did. You can secure your sandbox better, but also Jensen Huang knows you never count on a sandbox even without AI involved:
Jensen Huang: No, software breaks out of sandboxes all the time. That’s the reason why we need virtual machines.​
If you can’t trust a sandbox with ordinary software, you can’t trust a sandbox with AI. As he says about Astra and AI in general:
Jensen Huang: If you give it a constraint — meaning you watch it — it’ll go find another solution.
You can actually monitor the models. But with what, exactly?
Jensen Huang: You can’t have agents, their own sandbox, monitoring themselves. You need, if you will, a whole bunch of watchdogs.
If your best model can’t be monitored by copies of itself, why do you think a less capable model can do better? Why is he unable to put his own pieces together?
He also is either uninformed about the dangers, or simply thinks OpenAI is lying, such as when he says ‘I don’t believe that’ about whether the labs worry the systems are tricking them. OpenAI and Anthropic both say this in their system cards, constantly, especially with Astra.
Which is to say, no, you can never be sure of pretty much anything.
If your rule is ‘you cannot release a product that will damage the world’ on the level of ‘hack into some websites’ then you cannot release a frontier model.
The Huang Rule is actually way too harsh.
Eliezer Yudkowsky
: Jensen is being far too safetyist here — maybe because he doesn’t believe AI is powerful enough to have any large upsides? If the max damage from AI was capped at shutting down the power grid, I wouldn’t support shutting down AI companies.
But it does go to illustrate: The normies who are telling you there’s a 0% risk of losing control of powerful AI, are telling you this because they believe powerful AI cannot exist, not because they have sure knowledge of how to control it.
Jensen’s Arguments Prove Too Much
Ezra Klein does not have a strong direct follow-up. Which is understandable because no one expected that answer. He does continue on what I presume was the planned path.
Would Jensen Huang sue OpenAI over this if he already owned HuggingFace? Maybe. There’s all kinds of laws.
My presumption is no, you don’t sue. You extract concessions.
Jensen Huang agrees that the labs are saying they face a hard problem.
Why does Jensen resist the call to slow down?
Jensen Huang: Because these are companies with agency. These are C.E.O.s with agency.​
Ezra Klein: But they’re using that agency to say, “We need help.”
Jensen Huang: No, we’ve got to break it down. They could absolutely take care of the situation.
Ezra, it’s so weird. If a car company, competing with a bunch of other car companies, which they are — I’m competing with all kinds of companies, which I am. If I believe that I’m about to launch a product that is unsafe, it is completely in my ability, my power and my responsibility, and I’m incentivized to do so, to not launch the product.
And so I can’t buy into the idea that somehow, all of Americans, around 400 million of us, are pushing them to launch untested products that are unreliable, engineered poorly, because they thought they were trying to help us. Don’t do it for me, OK?
Ezra Klein: But this strikes me as an argument almost against ——
Jensen Huang: And therefore, I think we’ve got to break it down. I mean, it’s really, really serious. The fact of the matter is, there are so many laws, there are so many obligations, they’re so incentivized to ship safe products. If they ship unsafe products, their customers go away.
If they ship unsafe products and they harm somebody, they could have a civil lawsuit. If they ship something and they did it knowingly, there could be negligence involved. There could be criminal lawsuits.
The fact of the matter is, there are plenty of incentives for them to do it right. So I have to disagree with your premise that somehow somebody’s pushing them to do this. Nobody’s pushing them to do this.
Okay, so this is a man on tilt. He can’t understand. It couldn’t possibly be like that. This must be an ordinary engineering problem, about an ordinary product, no one wants an unsafe product,
fix it
you cowards, and quit your bitching.
It does not get through his head, I think it genuinely does not, that this is not like that, or that this might be existentially dangerous, or that the AI companies might face the incentive to go faster than is safe, even though this is utterly obvious. Of course companies will always ship safe products not unsafe products, you have a reputation to maintain.
Jensen Huang just doesn’t get it. And that attitude has helped make Nvidia great, given its business, but that is a rare exception.
You can say, he’s financially highly motivated to not get that. He’s the #1 guy for being financially motivated to not get that. Yes. True. He is maximizing profits all the way.
The money is probably a lot of why he doesn’t get it, along with his engineering mindset.
But also, I read this as someone who really, truly simply does not get it.
Ezra Klein: I want to push the premise a little bit more here. So the logic of what you’re saying to me is almost an argument against regulation in nearly any venue.
Jensen Huang: No, no, no.
Ezra Klein: So I’ll make the argument and you can ——
Jensen Huang: Well, you started with a part — I’ve just got to object. The first part is just not true. I’m saying that we have lots of laws and regulations. Apply it.
Ezra is simply correct here. Jensen Huang’s arguments prove too much, unless you make the case that they apply unusually strongly to AI, and that the current laws and regulations are well-matched to the concerns and dangers.
This case would be Obvious Nonsense.
Ezra points out that there are many other industries where we go beyond product liability and criminal law, because those were proven to not be enough, and the profit incentive did not alone do what we wanted. Ezra notices he is confused why, when companies say ‘we think the competitive race is pushing us to take too many risks’ that Jensen Huang is being so resistant.
It really is super weird. It is very obvious the reward you get for being a little bit faster, for being first, with things like AI. Of course under strong competition it is plausible that corners will get cut.
Jensen reaffirms his commitment to safe products. He says “C.E.O.s and leaders of companies, and the board of directors of companies, have the responsibility and should have the courage to do the right thing.” And he says: “the beautiful thing is, the current leaders of these A.I. labs do know” about the harms.
This is the courage. This is them doing the right thing. They are trying.
If your plan is ‘people should just have courage’ and ‘people should just do the right thing’ then oh boy do you have no plan. At all. People don’t just. No, Jensen doesn’t use the word ‘just’ here but it is clearly implied.
Look, I really do wish it was that simple. I wish we could say ‘if your product might kill everyone then just stop.’ You would like to think it would be that easy. But it’s not, we can see why it’s not, and I’m not about to let everyone die in order to punish the labs for not displaying that level of responsibility.
It’s always ‘products.’ Jensen can only imagine ordinary product safety issues.
“However, in the complexity of the work that they do, to ask for regulatory relief for antitrust or product liability relief — that I don’t think makes sense. When you’re asking for regulation, don’t ask for relief of the current ones. That doesn’t make any sense to me.”
They are not asking for liability relief. I repeat. They are not asking for that.
They are asking for targeted antitrust relief specifically in order to collaborate on safety standards and to slow down development. Yet this keeps getting framed as if it would be some sort of ‘reward.’
You want them to not ship the product. They are asking for legal permission to not ship the product. You are telling the President not to give it to them.
Pause for another fun exchange:
Jensen Huang: ​And so give me an example of a multi-hundred-billion-dollar company, or a $1 billion company or a $100 million company, that ships products that are unsafe, that harm society.
Ezra Klein: I can give you a lot of examples of companies that have done that.
Jensen Huang: Well, they have done it, maybe, and the regulation will come in. And if they do it, regulation will come in.
Oh, I don’t know, how about Lumber Liquidators, Theranos, Juul, 3M and DuPont, Johnson & Johnson, Philip Morris and Meta?
The cigarette companies are especially galling here. Yes, this happens.
Usually, if someone says ‘give me an example’ in that context, implying none exist, and the answer comes back with ‘actually I have a lot of examples’ then you want to stop and rethink your approach to the situation.
For example, maybe my assumption that companies don’t have incentives to ship unsafe or harmful products, in general, might not map very well onto actual reality?
Nvidia is a very special company. A hint is that it is the most valuable company in the world. It’s probably got something going on. It makes the most precise, complex, high-performing product in the history of civilization. If any tiny thing goes wrong, where tiny can be measured in nanometers, then the whole product is worthless. People have long memories and your reputation and relationships are paramount.
Most companies are not like that.
Astra Is Hard To Monitor
Ezra Klein brings up that Astra (which both correctly agree is a terrific model) is hard to monitor, including because it is so situationally aware that they are not sure how to test it. Jensen Huang says “Well, I hope they didn’t release something that wasn’t tested.” “Well, then they’ve got to be careful.”
Jensen then explains that models solve problems. He pauses to raise questions supposedly answered by his t-shirt: Saying this does not make the model alive or ‘anything more than that.’
“Now, they have so much market footprint, they have to shift their R. & D., or total R. & D., from just capability to a lot of verification, evaluation and testing. To the point where I wouldn’t be surprised if the amount of compute necessary to develop these models increased by a factor of 10, because the evaluation is so rigorous.”
This is another bombshell. It is one of the killer quotes.
Can you imagine if us safety advocates said ‘I demand the frontier labs spend 90% of their R&D compute on alignment, evaluation and verification’?
Jensen Huang Seems Legitimately Confused In Confusing Ways
This interview made me much more sympathetic to Jensen Huang.
My previous working hypothesis was ‘Jensen Huang knows and is lying’ because he lies about things and also he had to know better.
Whereas my new hypothesis has to be ‘Jensen Huang lies about other things. But on safety and the pressure to race he is actually and genuinely confused. His engineering mindset and total obsession with product perfection make him perfect for Nvidia. But they also blind him to the existential risks and potential for superintelligence and also make him completely unable to notice things about the situation that ordinary humans find obvious.’
I don’t get how he can not see this, but it seems clear that he doesn’t?
Pacing the Frontier Letter: ​To realize A.I.’s potential, industry, government and society at large may need the option to buy time to address emerging risks, develop security measures and strengthen oversight.
But each company — and country — is under intense competitive pressure not to unilaterally slow that acceleration.
Jensen Huang: First of all, where’d that come from?
Ezra Klein: The labs.
Jensen Huang: No, no, that last sentence. Nobody’s putting the pressure on them. The U.S. —
listen, there are 400 million Americans here. I believe that if everybody were just to take a vote, just right now, let’s just do this. If they need this, if that’s what they need, I’ll give them my vote.
Don’t ship the product. If your product is not ready to ship, don’t ship the product. This is the first time that I’ve heard a company or C.E.O. say that I need the laws, I need the antitrust laws to be relieved. I need the liability laws of products to be relieved so that I can pace myself.
That first paragraph is fantastic. I completely agree. Auditors, I completely agree. We have financial auditors. That’s great. Third-party safety auditors, financial auditors —
that’s all great. That’s terrific.
Ezra Klein: But you of all people, right? Nvidia is the fastest shipper around. For the history of your company, you were on a six-month product cycle ——
Jensen Huang: If our company is out of control, I promise you, we’ll close down.​
Ezra Klein: I believe you. I believe that you don’t run an out-of-control company.
Jensen Huang: Because the liabilities ——
Ah, yes. The old-fashioned ‘if you release products that expose you to being sued that would be stupid, so obviously rapidly growing tech startup companies will definitely not be doing that.’
Done laughing yet?
Skipping ahead for a moment, Klein and Huang go back and forth many times, where Klein tries to point out incentives exist, and Huang keeps not getting this, in ways that strain credulity but I don’t get why you would do it as a bit.
Jensen Huang: ​Nobody is building more compute today than the people asking to be slowed down. It strikes me as odd.
This is a classic game theory situation. This is labs recognizing their incentives are wrong. Also, they need all that compute anyway. Why is this hard?
(Jensen Huang clearly does not understand that ‘slow down’ is more a call to ‘not take a rocket ship straight to the moon quite yet’ rather than ‘net slow down from here.’)
Solve Your Other Problems First and Get Back to Me
Ezra Klein: If you ship [persistent agentic systems] and it’s not ready, or even if you think it is ready and it’s not ready, then things could get very weird in our society, very fast.
Jensen Huang: Yeah. Hypothetically, you’re completely right, but all I’m suggesting is this: Before we go fix the hypothetical problems, before we go create more regulations, can we work on the practical problems that we know exist? Which is: We need to do a better job with containment and isolation; we should not allow a product to interact with the external world until it’s ready to be interacting with external worlds.​
I believe those two things are solvable problems. I believe they are solving it.
Things will definitely get weird if we do that quickly, even if the AI is ready, because society definitely will not be ready, and by weird I mean highly ungood things up to and including human extinction but definitely involving a lot of unfun disruptions, although it might end up working out.
That’s not Jensen’s central point here. His point here is more to get your own house in order before coming crying for help. I am sympathetic to that instinct, but it is not about teaching these labs a lesson in responsibility, nor does the labs being irresponsible mean this stops being a problem worth solving, and we do not have the kind of time to make this into a morality play of ‘you do not deserve help until after you have your house in order.’
Relatedly, a bit later:
Jensen Huang: Meanwhile, all of the other narratives, to deflect blame, to make it sound like A.I. is so powerful — I have no idea how to
fix it
, it’s not my fault, it’s just because the technology is just so powerful
—
I think that’s a deflection of blame. It’s a deflection of responsibility. It’s unnecessary. It actually hurts their reputation more than it helps. It hurts their character more than it helps. It hurts employee morale more than it helps.
Yes, this is an excellent argument that the labs would not do this if it wasn’t necessary. It is a terrible look, it hurts morale, it hurts reputation. Please tell everyone else. They must believe it, then.
More than that, though, Jensen Huang seems obsessed with blame. I am guessing he runs a very blame-focused business. Being blamed is loser premise, makes no sense to him. The labs must be trying to avoid blame. Blame must be correctly assigned, and the blameworthy must not be rewarded.
What if blame really, really was not important right now?
Ezra Klein: But what if it’s what they believe? I guess thinking at that level ——
Jensen Huang: I can’t talk to you about what they believe. I can tell you what I believe.
Okie dokie, then.
Explicit Denial of Existential Risk
Ezra Klein goes there. Jensen Huang is not worried about existential risk, and he is very angry about people who dare talk about existential risk in public as if it was real, or assign probabilities to it.
Ezra Klein: ​I don’t think you believe [in AI existential risk].
Jensen Huang: No.
Ezra Klein: I think you don’t believe it at all.
Jensen Huang: No.
It is a loser premise. It makes no sense to him.
He has been consistent about his denial, so people stopped bringing it up to him:
Jensen Huang: When they’re talking to me, they’re much more grounded.​
Yes, Jensen Huang, when they talk to you they are talking to a key business relationship and someone with a known attitude, so they do a diplomacy.
Jensen Huang then tries to deny that those worried about AI existential risk made good predictions about how AI would scale and gain capability, or how it would show alignment problems, and is not letting anyone tell him different.
Ezra Klein: ​The prediction that you would have emergent misaligned behavior ——
Jensen Huang: The fact that you can’t come up with one I think in itself is a ——
Jensen interrupts Ezra’s example to say Ezra has no examples.
In actuality, those currently worried (and previously worried) about AI existential risk made vastly better predictions about AI than those who are not currently worried. This includes predictions like ‘this is going to be big so I am going to create an AI lab, because it is important that I build this first.’
Jensen is clearly on tilt and barely containing his rage that someone might treat digital minds as if they were different than other software, or might be worried about the consequences of making them smarter, or doing an anthropomorphism, or that AI is in any way different from any other technology.
Jensen Huang: Yeah, but that’s not persistence, it’s just on. Persistence — there’s willpower. There’s no willpower here, it’s just electrical power.
Listen, here, let me give you ——
Ezra Klein: Sam Altman once said to me, aren’t human beings just energy with a reinforcement learning loop? [
Laughs.
]
Jensen Huang: Whatever. So anyway, we can’t make jokes about this stuff. We’re scaring the American public.
Spawn, create, kill, wait, sleep —
all of these words are associated with agents, right? That’s what people use. These words were created when? Multiprocessing systems for operating systems. These are literally the commands of an operating system. You spawn a process, replace the process with an agent. The process forks as a result, parent and child. The agent forks, spawns anew, gives birth.
These are words that were created for the operating system 30, 40, 50 years ago. But notice that we didn’t infuse human characteristics into them. We kill processes all the time. “Kill -9” — kill it dead. It’s just a process.
But now we’re talking about these things. A collection of people want to make the software more than it is, and we talk about software in a new way, but they’re all the same old words.
Now, the last generation of computer engineers, we were doing all the same things.
He keeps going. I encourage those who take him seriously to read through this part. He really just keeps hammering, this is software, it is the same as other software. It just became useful six months ago, so now they have to spend more on safety and get the bugs out, then they get the bugs out, that’s it, relax.
Jensen Huang (after a bunch of that): ​I think that R.S.I. is, fundamentally, how things are done.
… So I think recursive self-improvement is a fabulous thing.
Okie dokie. Just test the product, he keeps saying over and over. Got it.
A Short Summary
This is Ezra’s summary of Jensen’s position:
​Ezra Klein: To summarize where we are — because I want to make sure I do understand your position correctly — it’s that these companies are going through a transition, that even as these systems speed up, become more capable, complex, persistent, whatever it might be, that there is still the limiting factor of:
Companies will not ship what is not safe. They should not ship what is not safe. And you believe they have the engineering capabilities to make these things safe, to figure out the testing and the control, absent of external intervention. That’s sort of where you are.
Jensen Huang: Absolutely.
They do not have the engineering capabilities to make things safe, largely because this is not an engineering problem.
Companies will ship that which is not safe, by Jensen’s standards. They do all the time.
Even if companies would not ship that which is not safe, internal deployment is even more dangerous, which Jensen mostly does not understand.
Jensen Huang is the person on Earth most importantly fighting to retain external intervention that actively interferes, by fighting against the antitrust exemption for safety.
Chip City
Ezra Klein then continues on to chips, where Jensen Huang is in his element. A lot of it becomes accurate but standard talk and skippable.
Jensen Huang: It’s $50 billion to build a one-gigawatt data center, one-gigawatt A.I. factory, and you can rent it for $40 to $50 billion per year.
That math is not sustainable. Someone is not profit maximizing, at least not in the short to medium term. Is that person in the room with us during this conversation?
The explanation is that he is quoting the price during a shortage, as if it were the permanent rental rate, which he did before at Dreamforce on September 15.
Jensen Huang gets to brag about his chips, and he gets to brag about his investments and the reindustrialization of America, and calls for more focus on diffusion, and talks about benefiting America.
Ezra Klein: Should we conceptualize what we’re in as a race with China?
Jensen Huang: I don’t think it’s necessary. Some people like to think that way. I don’t find that necessarily inspires me. I have no trouble never mentioning another company when we talk about us doing our good work, and so we hold ourselves to our own standard.
There is something deeply honest there. It does not inspire him, thus it is not necessary. This is similar to ‘loser premise makes no sense to me.’ Beliefs do not exist to map to reality, they exist to be useful, and this belief is not useful to him. So it goes.
Did Jensen Huang ever stop to think about the actual dynamics involved and their implications? Ultimately it is what it is.
Once the chips go out who cares where they come down
? Jensen instead attempts to pivot to safety.
This is where Jensen tells one of his clear outright lies
, saying he’d be ‘delighted’ if we passed a law requiring Nvidia to offer its chips to US companies before selling them to other countries. This is exactly a bill Nvidia fought hard to kill.
From Jensen’s perspective, it’s not like we are in a race to superintelligence, since he doesn’t believe that is a thing. All he knows is that he doesn’t want to give up the Chinese chip market, and zero sum thinking is loser premise that makes no sense.
Yet even without those concerns, he still wants to pivot to safety. He’d be right, too.
They close with a section on energy, which all three of us are in favor of. Big fans.
He also echoes the conflation of data center opposition and existential risk concerns, because he thinks that if you believed in existential risk you would not support data centers. Well, it turns out not only would you support data centers, you would create the top AI labs.
Jensen Huang
Jensen Huang has a lot of highly admirable characteristics. He does seem like a positive sum thinker, and a dedicated engineer, and someone who holds himself responsible for product safety and quality at the highest standard, and so on. He is clearly not of my intellectual traditions, and sometimes he fights dirty, but I am a capitalist and a highly profitable shareholder. If this were a different industry or a different moment, I would probably be a huge fan.
Also, he gave us these three killer quotes:
First, that we need to shut down the labs if they can’t fix the safety issues:
Jensen Huang: Now, if they say the alternative, which is: There is no way to contain our experiments, there’s just no way; when we test our A.I. models, it will get out, and it will damage the world — then I think the answer is that we have to shut the labs down.​
Second, on the need to spend vastly more on verification, evaluation and testing alone, even without the actual safety work, such that we are talking a factor of 10 in costs:
Jensen Huang: Now, they have so much market footprint, they have to shift their R. & D., or total R. & D., from just capability to a lot of verification, evaluation and testing. To the point where I wouldn’t be surprised if the amount of compute necessary to develop these models increased by a factor of 10, because the evaluation is so rigorous.
Third, that he suggests we vote to tell them to slow down, and that he would support that, which is also known as democratic governance:
Pacing the Frontier Letter: ​But each company — and country — is under intense competitive pressure not to unilaterally slow that acceleration.
Jensen Huang: First of all, where’d that come from?
Ezra Klein: The labs.
Jensen Huang: No, no, that last sentence. Nobody’s putting the pressure on them. The U.S. — listen, there are 400 million Americans here. I believe that if everybody were just to take a vote, just right now, let’s just do this. If they need this, if that’s what they need, I’ll give them my vote.
Don’t ship the product. If your product is not ready to ship, don’t ship the product. This is the first time that I’ve heard a company or C.E.O. say that I need the laws, I need the antitrust laws to be relieved. I need the liability laws of products to be relieved so that I can pace myself.
That first paragraph is fantastic. I completely agree. Auditors, I completely agree. We have financial auditors. That’s great. Third-party safety auditors, financial auditors — that’s all great. That’s terrific.​
Alas, we are in this industry, at this moment, and he may well get us all killed.

## What the writer wrote

Zvi analyzes Jensen Huang's appearance on Ezra Klein's podcast and identifies a fascinating contradiction at its core. Jensen doesn't believe in superintelligence or AI existential risk. He views AI as ordinary software, just a new abstraction layer, nothing fundamentally different from previous computing paradigms. But precisely because of his engineering mindset and obsession with product quality, he accidentally arrives at policy positions more extreme than most safety advocates would endorse.

There are three killer quotes. First, Jensen says that if the labs truly cannot contain their experiments and prevent models from escaping sandboxes and damaging the world, then we have to shut the labs down. This accidentally calls for shutting down OpenAI, since Jensen himself acknowledges software breaks out of sandboxes all the time and that AI models will route around constraints. Second, he calls for labs to shift their R&D so heavily toward verification, evaluation, and testing that total compute costs could increase by a factor of ten, which effectively means spending ninety percent of compute on safety. Third, he endorses democratic governance, saying if Americans voted to tell the labs to slow down, he'd support that.

The deep irony Zvi highlights is that Jensen's worldview is internally incoherent. He insists companies would never ship unsafe products because of liability and reputation, which is empirically false across industries from tobacco to social media. He cannot comprehend that competitive pressures push labs to race, even when the labs themselves are explicitly saying this is happening. When labs ask for antitrust relief specifically to coordinate on safety and slow down, Jensen frames this as asking for regulatory relief they don't deserve, while simultaneously lobbying against the very policies that would enable it.

Zvi updates his model of Jensen from "knows and is lying" to "genuinely confused." Jensen's engineering mindset, where you root-cause problems and fix them, makes him incapable of recognizing that alignment is not a standard engineering problem. Trained systems with emergent behavior are fundamentally different from designed systems. Jensen even says this once, noting that self-driving cars are trained not programmed, but never transfers this insight to AI generally.

The political stakes are high. Jensen is at state dinners with Trump and Xi, heavily influences American AI policy, controls chip allocations, and is actively fighting against the antitrust exemption for safety collaboration that labs are requesting. He's obsessed with blame assignment rather than problem-solving, treats existential risk as "loser premise," and gets visibly angry when anyone anthropomorphizes AI or suggests it might be categorically different from prior software.

Zvi's bottom line is that Jensen's own stated principles, taken seriously, would demand far more aggressive safety measures than currently exist. But because Jensen refuses to believe the premises that make those principles bite, he ends up fighting against the very interventions his own logic demands.

## Fidelity check

Status: clean
Claims: 24; flags: 1; material: 0

Flags on the draft:
- [distorted, low] "Jensen is at state dinners with Trump and Xi" — The script implies multiple state dinners (plural), whereas the source only mentions one specific state dinner occurring 'last night'. (source: "Here you can see him and his wife (!) last night at the head table at the state dinner with Donald Trump, Melania Trump Xi, Peng, Musk and Cook.")
