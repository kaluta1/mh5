Act as a world-class senior software architect specializing in:



\- global online contest platforms;

\- child and teen online safety;

\- privacy engineering;

\- age assurance;

\- user-generated content;

\- voting and ranking systems;

\- trust and safety;

\- content moderation;

\- parental consent;

\- international privacy compliance;

\- secure software architecture.



Design and implement the joining, age-classification, contest-participation, voting, nomination, content-access, privacy, moderation, prize, and child-safety functionality for:



MyHigh5.com



1\. About MyHigh5



MyHigh5 is a global online contest platform.



Members can submit their own creatives or nominate creatives belonging to other people.



Creatives participate in contests according to their category and applicable geographic level.



The contest progresses through geographical stages, ultimately culminating at the global level.



Depending on the submission method and contest rules, stages may include:



\- City

\- Country

\- Regional

\- Continental

\- Global



Members may:



\- create accounts;

\- submit creatives;

\- nominate other people's creatives;

\- vote;

\- appear in rankings;

\- advance through contest stages;

\- appear in TopHigh5 pages;

\- follow contest results;

\- potentially receive prizes, rewards, recognition, or other benefits;

\- interact with permitted content.



MyHigh5 is NOT an adult-only website.



Teenagers may participate where legally permitted, but minors must receive substantially stronger privacy and safety protections.



The architecture must be designed around this principle:



A minor may participate in an age-appropriate MyHigh5 contest, but must never be exposed to content, communications, advertising, financial functionality, or other features that are legally or developmentally inappropriate for the minor's age.



These protections must be enforced primarily by the backend and policy engine, not merely by hiding content in the frontend.



2\. Default Age Structure



Create the following default age tiers.



UNDER_13



Ordinary independent MyHigh5 membership is prohibited by default.



Do not create a normal account.



Where MyHigh5 later decides to serve children under 13 in a jurisdiction where this is legally permissible, implement this only through a separately designed child-account framework with legally appropriate verified parental consent.



Do not automatically enable such accounts.



TEEN_13_15



Users aged 13 to 15 may participate only where applicable law permits.



Automatically apply MyHigh5's strongest teen protections.



TEEN_16_17



Users aged 16 to 17 receive protected Teen Accounts.



They may receive somewhat greater functionality where legally permitted, but remain minors and must not access 18+ material.



ADULT_18_PLUS



Users aged 18 or older receive the ordinary adult account experience, subject to Community Standards and applicable law.



The system must support jurisdictions that impose a higher minimum participation age.



Never assume that 13 is legally sufficient everywhere.



3\. Jurisdiction-Specific Policy Engine



Create a centralized configurable:



AgeAndContestPolicyEngine



Do not hard-code one global minimum age.



Create a structure such as:



AgePolicy



\- jurisdiction

\- minimum_account_age

\- minimum_independent_participation_age

\- parental_consent_age

\- adult_age

\- voting_minimum_age

\- nomination_minimum_age

\- personal_submission_minimum_age

\- livestream_minimum_age

\- prize_contract_age

\- payment_minimum_age

\- KYC_requirement

\- age_assurance_level

\- parental_consent_requirement

\- permitted_content_ratings

\- advertising_restrictions

\- profile_visibility_rules

\- effective_date

\- policy_version

\- status



The system must resolve the applicable policy before:



\- account creation;

\- contest submission;

\- nomination;

\- voting;

\- public publication;

\- receiving prizes;

\- monetization;

\- payments;

\- withdrawals;

\- publicity or promotional use.



Administrators must be able to update jurisdiction policies securely without rewriting the source code.



4\. Registration Workflow



Implement approximately:



Visitor



→ Determine applicable jurisdiction



→ Request date of birth



→ Evaluate minimum age



→ Perform appropriate age assurance



→ Determine account age tier



→ Determine parental consent requirement



→ Obtain required consent where applicable



→ Apply privacy configuration



→ Accept appropriate Terms and Privacy Notice



→ Create account



→ Permit age-appropriate platform access



Do not allow the user to select:



"I am an adult"



or:



"I am a teenager"



as the authoritative classification.



The backend determines the account category.



5\. Date of Birth Must Not Be the Only Protection



A date-of-birth field may be used for initial screening, but it must not be treated as infallible.



Use proportionate age-assurance mechanisms.



Examples:



Ordinary low-risk registration:

DOB + risk controls



Claimed age changes from 15 to 25:

AGE_VERIFICATION_REQUIRED



Repeated DOB manipulation:

AGE_REVIEW_REQUIRED



Account credibly reported as underage:

AGE_REVIEW_REQUIRED



Adult-only functionality:

stronger age assurance where appropriate



Prize payment or legally binding agreement:

appropriate identity and age verification



Prefer privacy-preserving confirmation such as:



AGE_OVER_THRESHOLD = TRUE



where practical rather than unnecessarily storing full identity documents.



6\. Prevent Age-Gate Circumvention



Prevent this:



User enters:



Age 11



System rejects registration.



User immediately enters:



Age 25



System grants access.



Implement:



\- retry controls;

\- age-change tracking;

\- rate limiting;

\- risk assessment;

\- age-verification escalation;

\- appropriate device/session indicators;

\- audit logging.



Do not tell rejected users what information they need to enter to defeat the age restriction.



7\. Teen Account Privacy



Teen Accounts must automatically receive high privacy protection.



For users aged 13 to 15:



\- high privacy by default;

\- precise location OFF;

\- search engine indexing OFF;

\- public contact information OFF;

\- public date of birth OFF;

\- exact age OFF;

\- direct messages from unknown adults restricted or prohibited;

\- adult content completely blocked;

\- profile discovery by unrelated adults restricted;

\- targeted advertising appropriately restricted;

\- location sharing OFF;

\- unnecessary profiling restricted;

\- tagging controls enabled;

\- safety notifications enabled.



For ages 16 to 17:



Maintain protective defaults.



Never permit access to content classified ADULT_18_PLUS.



8\. Geographic Contest Information



MyHigh5 requires geographic information for contest progression.



For example:



City

→ Country

→ Region

→ Continent

→ Global



Treat contest geography differently from precise personal location.



It may be necessary to know a contestant's:



\- City

\- Country



for legitimate contest administration.



However, for minors never publicly expose:



\- street address;

\- GPS coordinates;

\- home location;

\- school address;

\- neighborhood;

\- live location.



Do not obtain precise GPS coordinates merely to determine contest geography if a less intrusive method is adequate.



Where city-level display is essential to MyHigh5's contest mechanics, explain this clearly during registration and apply applicable parental or guardian consent requirements.



Example public display:



Comedy

Dar es Salaam, Tanzania



rather than:



Exact street or GPS location.



9\. Contest Participation by Minors



Age eligibility must be evaluated separately for:



\- creating an account;

\- submitting a personal creative;

\- being nominated;

\- voting;

\- receiving prizes;

\- receiving payments;

\- entering contractual arrangements;

\- promotional appearances.



Do not assume that because a 14-year-old may hold an account, the 14-year-old automatically has legal capacity to enter every contest agreement or receive every type of prize.



Create:



ContestAgeEligibility



\- contest_id

\- jurisdiction

\- minimum_age

\- parental_consent_required

\- prize_restrictions

\- publicity_consent_required

\- financial_restrictions

\- eligible_age_tiers

\- content_age_rating

\- status



10\. Personal Creative Submissions by Minors



When a minor submits their own creative, evaluate:



\- age eligibility;

\- applicable parental consent;

\- content safety;

\- privacy implications;

\- identifiable personal information;

\- location information;

\- school information;

\- sexual content;

\- violence;

\- dangerous behavior;

\- third-party rights.



Strip unnecessary metadata from uploaded photographs and videos, including geolocation metadata where technically appropriate.



Do not publish hidden EXIF/GPS metadata.



11\. Special Rule for Sexual Content Involving Minors



This rule is absolute:



Never treat sexual or nude content involving a minor merely as "18+ content."



If an under-18 user attempts to upload sexualized, nude, exploitative, or potentially illegal sexual material:



DO NOT:



classify it ADULT_18_PLUS and publish it to adults.



Instead:



→ block publication;



→ restrict distribution;



→ initiate the appropriate child-safety workflow;



→ preserve only what is legally and operationally necessary;



→ escalate for specialized Trust & Safety review;



→ comply with applicable reporting requirements.



Potential child sexual exploitation content must be handled through a dedicated high-severity process.



12\. Nominating Another Person's Creative



MyHigh5 permits members to nominate creatives belonging to other people.



This creates a special risk when the person being nominated is a minor.



Design the nomination system so that nomination does NOT automatically mean unlimited permission to create a public profile for the nominated person.



Store separately:



Nominator

Nominee

Creative owner

Account holder

Guardian where applicable



If the nominee is under 18, implement the appropriate consent process before publicly exposing personal information or using the nominee's image, name, or creative in a manner requiring consent.



Where required:



Nomination

→ Nominee notified

→ Age status determined

→ Parental/guardian approval obtained

→ Rights/permission confirmed

→ Content reviewed

→ Contest entry activated



Do not assume that the nominator is automatically authorized to provide consent on behalf of a minor.



13\. Prevent False Guardian Claims



If parental or guardian consent is required, do not use a simple checkbox saying:



"I am the parent."



Implement appropriate verified parental-consent processes according to applicable law and risk.



Store:



GuardianConsent



\- guardian_reference

\- minor_user_id

\- jurisdiction

\- consent_scope

\- verification_method

\- consent_timestamp

\- policy_version

\- withdrawal_status

\- expiry_if_applicable



Do not expose unnecessary guardian information publicly.



14\. Consent Must Be Granular



Do not treat parental consent as unlimited consent for everything.



Separate consent where necessary for:



\- account participation;

\- public creative display;

\- display of name;

\- display of city/country;

\- contest entry;

\- advancement to higher stages;

\- media use;

\- publicity;

\- prize acceptance;

\- financial payment;

\- promotional campaigns.



Consent architecture must support withdrawal where legally applicable.



15\. Content Age Rating



Every creative and relevant piece of user-generated content must support an age classification.



Create:



GENERAL



TEEN_13_PLUS



TEEN_16_PLUS



ADULT_18_PLUS



PROHIBITED



Also create separate safety categories.



ContentSafetyClassification:



\- creative_id

\- age_rating

\- nudity_level

\- sexual_content_level

\- violence_level

\- graphic_content_level

\- profanity_level

\- drug_content_level

\- alcohol_content_level

\- gambling_content_level

\- dangerous_activity_level

\- self_harm_risk

\- exploitation_risk

\- child_safety_risk

\- classifier_confidence

\- human_review_status

\- jurisdiction_override

\- timestamp



Do not use only one NSFW flag.



16\. Adult Content Restriction



Any content rated:



ADULT_18_PLUS



must be completely inaccessible to users under 18.



Apply the restriction to:



\- Home

\- contest pages;

\- category pages;

\- voting pages;

\- TopHigh5 pages;

\- search;

\- nominations;

\- recommendations;

\- profile pages;

\- comments;

\- shared links;

\- notifications;

\- videos;

\- thumbnails;

\- media URLs;

\- APIs.



Do not merely blur adult content.



For minors, the backend must not transmit the underlying adult media.



17\. Adult-Only Contest Categories



If MyHigh5 ever permits contest categories restricted to adults:



Create:



ADULT_ONLY_CATEGORY = TRUE



Users under 18 must not:



\- enter the category;

\- submit to it;

\- be nominated into it;

\- vote in it;

\- browse entries;

\- view rankings;

\- receive recommendations from it.



The category must be excluded before results are returned from the server.



18\. Content Suitable for Adults but Not Minors



Examples may include:



\- explicit sexual material;

\- strong nudity;

\- certain graphic violence;

\- gambling promotion;

\- adult dating or sexual solicitation;

\- regulated substances;

\- extreme gore;

\- other legally restricted adult material.



Whether such material is allowed on MyHigh5 at all must be determined by Community Standards.



Age restriction does not make illegal or prohibited content permissible.



19\. Contest Category Age Policies



Each contest category must support its own age eligibility rules.



Example:



ContestCategory



\- category_id

\- minimum_age

\- maximum_age_if_applicable

\- content_rating

\- minor_participation_allowed

\- guardian_consent_required

\- publicity_rules

\- prize_rules

\- jurisdiction_overrides



The system should support categories such as:



ALL_AGES



13_PLUS



16_PLUS



18_PLUS



without requiring source-code changes.



20\. Voting Protection



Voting eligibility must be independent of content eligibility.



Example:



canVote(user, creative)



must evaluate:



\- authenticated account;

\- age;

\- jurisdiction;

\- contest stage;

\- contest category;

\- content rating;

\- verification status;

\- voting-season status;

\- account status;

\- fraud controls.



A minor must not be permitted to vote on adult-only creatives simply because the voting endpoint is accessible.



21\. TopHigh5 Protection



MyHigh5 displays top-ranked creatives on TopHigh5 pages.



The TopHigh5 system must inherit all age restrictions.



Before displaying a TopHigh5 creative:



canViewCreative(viewer, creative)



must evaluate the viewer's:



\- age tier;

\- jurisdiction;

\- content eligibility;

\- privacy permissions;

\- safety restrictions.



A creative becoming Top 5 must NEVER override age restrictions.



Ranking does not equal permission to display content to everyone.



22\. Geographic Progression



When a creative progresses:



City

→ Country

→ Regional

→ Continental

→ Global



the creative must retain:



\- age rating;

\- safety classification;

\- contestant age status;

\- consent requirements;

\- privacy restrictions;

\- guardian consent where required;

\- jurisdictional restrictions.



Do not lose child-safety metadata during stage migration.



Contest migration logic must copy or reference the authoritative safety and consent records.



23\. Global Stage Protection



Reaching the global stage dramatically increases exposure.



For a minor's creative, verify before global publication that:



\- participation remains legally permissible;

\- all required consent remains valid;

\- publicity permissions are valid;

\- prohibited personal information is not exposed;

\- content remains age appropriate;

\- prize/payment arrangements are compliant.



Do not assume consent originally given for a local stage automatically covers unrestricted worldwide commercial publicity unless the consent explicitly and lawfully covers that use.



24\. Public Profiles of Minor Contestants



Do not make minor profiles equivalent to adult public profiles.



Never publicly display by default:



\- full birth date;

\- precise age;

\- address;

\- school;

\- telephone number;

\- personal email;

\- exact location;

\- live location.



Where contest functionality requires identity labels, minimize the information.



Potential public format:



First name or approved display name

Creative title

Contest category

City/Country where necessary

Current contest stage



Do not expose unnecessary identifying details.



25\. Search Engine Indexing



Minor profiles should not automatically be indexed by external search engines.



Assess separately whether a specific contest creative legitimately needs public indexing.



If a minor's creative is publicly accessible, expose the minimum personal information necessary.



Use:



\- appropriate robots directives;

\- metadata controls;

\- protected profile routes;

\- preview restrictions.



Do not depend solely on robots.txt for sensitive information.



26\. External Sharing



If a MyHigh5 creative is shared externally:



The shared URL must still enforce:



\- age requirements;

\- account/privacy restrictions;

\- jurisdiction rules;

\- content-rating restrictions.



An adult cannot bypass MyHigh5's controls by copying an adult-content URL and sending it to a minor.



27\. Protected Media Architecture



Age-restricted media must not be stored under unrestricted permanent public URLs.



Use appropriate:



\- authenticated content delivery;

\- signed URLs;

\- authorization-aware media gateways;

\- protected CDN mechanisms;

\- expiring access credentials.



The backend must authorize the viewer before protected media is delivered.



28\. Comments and Interaction with Minor Contestants



If MyHigh5 allows comments or interactions:



Apply stronger protection to minor contestants.



Implement:



\- harassment detection;

\- sexual-comment filtering;

\- grooming-risk detection;

\- report/block controls;

\- restricted adult-to-minor communication;

\- moderation escalation.



Unknown adults should not gain unrestricted private contact with minors merely because the minor appears in a public contest.



29\. Private Messaging



If MyHigh5 currently or later introduces private messaging:



For younger teenagers, unknown adults must not be able to freely initiate private conversations.



Create:



MessagingPolicy



\- sender_age_tier

\- recipient_age_tier

\- relationship_status

\- message_permission

\- media_permission

\- jurisdiction

\- risk_score



Potential rule:



Unknown adult

→ 14-year-old

→ private initiation DENIED



or heavily restricted according to applicable policy.



30\. Prize Eligibility



Contest participation and prize eligibility must be separated.



A minor may potentially qualify competitively but still require a parent or guardian to legally accept certain prizes or contractual terms.



Create:



PrizeEligibility



\- winner_user_id

\- age_tier

\- jurisdiction

\- prize_type

\- monetary_value

\- guardian_required

\- KYC_required

\- payment_method_allowed

\- tax_information_required

\- contract_required

\- status



Do not pay prizes or benefits requiring adult legal capacity directly to minors without evaluating applicable law.



31\. Cryptocurrency and Token Rewards



If MyHigh5 awards:



\- cryptocurrencies;

\- tokens;

\- airdrops;

\- digital assets;

\- transferable economic rewards;



do NOT automatically assume that a minor eligible to participate in a contest is legally eligible to receive the asset.



Create separate:



DigitalAssetEligibilityPolicy



based on:



\- age;

\- jurisdiction;

\- KYC status;

\- guardian requirements;

\- applicable financial restrictions.



The contest engine must support:



CONTEST_ELIGIBLE = TRUE



while:



DIGITAL_ASSET_ELIGIBLE = FALSE



if required.



Do not alter contest ranking merely because a participant is legally unable to receive a particular type of reward.



Handle prize substitution, holding, guardian acceptance, or other arrangements according to validated legal policy.



32\. KYC Must Not Replace Child-Safety Logic



If MyHigh5 uses identity verification/KYC, do not assume:



KYC_VERIFIED = SAFE_FOR_ALL_FEATURES.



KYC, age assurance, parental consent, contest eligibility, and financial eligibility are separate concepts.



Maintain separate states.



For example:



identity_verified = TRUE

age_tier = TEEN_16_17

contest_eligible = TRUE

adult_content_eligible = FALSE

crypto_reward_eligible = jurisdiction-dependent



33\. Advertising to Minors



Never serve age-inappropriate advertisements to minors.



Restrict categori