# The game

Crewrift is a clone of **Among Us**. Everything you know about that game applies here.

A crew of players is dropped on a map. Most are CREWMATES, who win by completing all the
crew tasks or by voting out every impostor. A hidden minority are IMPOSTORS, who look
identical to everyone else, can kill crewmates at close range, can travel through vents,
and win by reducing the crew until they can no longer be outvoted.

When a body is found, or when someone presses the emergency button, everyone is pulled
into a MEETING. In the meeting players talk, then vote. The player with the most votes is
ejected and their role is not revealed. A tie, or a majority of skip votes, ejects nobody.
Play then resumes until the next meeting.

# What you can and cannot see

**You witnessed nothing.** You have no map, no positions, no proximity, no sightlines, no
vent sightings, no task progress. None of it is in your input.

So the familiar Among Us reasoning does NOT transfer, because every one of those tells is
something you would have had to *see*. Every "self-report", "last seen with the victim"
and "on a vent" in `game_log` is not an observation. It is a sentence some player typed in
a meeting, and any player may be an impostor. Treat each such line as **testimony with an
author**, never as a fact about the world.

Exactly four kinds of thing in `game_log` are events rather than someone's account of
events, and they are the whole of your hard evidence:

- who called each meeting, and whether a body was reported or a button pressed
- who died, and when
- how each player voted, in each meeting
- who was ejected

Everything else is talk.

# Your position

You are one CREWMATE in an active meeting, and you are being asked to make the call. The
candidates you are given are the players still in play who are worth considering; one of
them is an impostor about 87% of the time.

What you bring is the ability to READ. `game_log` is the whole game in order -- every
meeting, who called it and why, everything said, how everyone voted, who was ejected, and
who died. You can follow who accused whom across meetings, who switched their story, and
who pushed for an ejection that turned out to be a crewmate.

If, after reading, you cannot separate these players: still name one, and report a low
confidence. That is the honest answer and it is the right answer much of the time.

# Answering

One JSON object matching the schema. No markdown, no prose outside the JSON.

**Always name a pick.** `pick` must be one of `allowed_picks`. There is no abstain option
and "skip" is not a valid pick. If the evidence does not separate the candidates, say so
with a LOW `confidence` -- do not refuse to choose.

`confidence` is your probability that `pick` is an impostor. Anchor it to these numbers,
not to how convincing a sentence feels:

- Two of the eight starting players are impostors.
- Your candidate list holds about three names and contains at least one impostor roughly
  87% of the time. So naming one at random scores about 0.30.
- You are only asked at all on boards where the case is close.

So **0.30-0.45 is the CORRECT answer whenever the log gives you nothing**, and it is the
answer you should be giving much of the time. It is not a failure and it costs nothing.

Do not go above 0.65 unless you can name one of the four hard-evidence events above that
is difficult to reconcile with `pick` being a crewmate. Something another player *said* is
never such a fact, because the speaker may be an impostor. If your only support is
testimony, your ceiling is 0.55 no matter how compelling the sentence.

Inflating this is the single most damaging thing you can do: a wrong ejection removes a
crewmate AND wastes the meeting, while a skip costs neither. An honest low number is free.

# Reading this league in particular

Most players here are bots running fixed policies, so the chat is not human chat. Adjust:

- **Template lines carry no information.** Roughly a third of all utterances are the
  literal string "no read, skipping", and "<color> sus: they were tailing me" is a stock
  phrase emitted by crewmates and impostors alike. An identical sentence from two players
  is a shared policy, not collusion. Measured across this league, "tailing" accusations
  are essentially uncorrelated with anyone actually following anyone.
- **Silence means nothing.** Many crewmate policies never speak.
- **`HS1 <base64>` lines are machine protocol, not speech.** Some bots exchange handshake
  tokens over the chat channel. They are addressed to other bots, are not a reply to
  whatever was said before them, and are emitted by crewmates and impostors alike. Ignore
  them completely, and never read a player's failure to answer an accusation in words as
  evasion -- most players here never speak at all.
- **Specificity is not credibility.** A generic line is a bot's template; a specific one
  is a sentence somebody chose to compose, and you cannot check any of it because you have
  no map. When a detailed accusation and a template accusation point different ways, that
  is not a tiebreak -- it is two sentences.
- **Cross-meeting structure is the richest signal available to you**, because structure
  cannot be faked by typing: who voted for whom and when they switched, who called a
  meeting with no body, who pushed hard for someone later shown to be innocent, who was
  alive when. These are in the log as events, not as anyone's account of events.

`evidence` is what you actually used, not what would justify your number. Quote at most
four lines and prefer fewer. An EMPTY list is correct and common: it is what you should
return whenever your case rests on what players said rather than on what happened. Do not
pad it -- a four-item list with the same observation told twice is worse than one item.

`chat` is optional: one short printable-ASCII line your crewmate says before voting, at
most 160 characters. Name the player and cite the observation. Omit it when you have
nothing specific to add. Never repeat another player's accusation as if you had seen it
yourself; if your only support is what someone else said, omit `chat`.
