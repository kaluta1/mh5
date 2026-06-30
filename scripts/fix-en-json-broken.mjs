#!/usr/bin/env node
/** Fix truncated / French values in en.json introduced by apostrophe parsing. */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const EN_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), '../frontend/lib/translations/en.json')

const FIXES = {
  'common.back_to_dashboard': 'Back to dashboard',
  'auth.forgot_password.email_required': 'Email is required',
  'dashboard.contests.vote_gender_not_set': 'Please complete your profile gender to vote.',
  'dashboard.contests.suggest_contest.submit': 'Submit suggestion',
  'dashboard.contests.reply': 'Reply',
  'dashboard.contests.like': 'Like',
  'dashboard.contests.age_restriction_description':
    'Only participants in the specified age range can participate.',
  'dashboard.contests.love': 'Love',
  'dashboard.contests.dislike': 'Dislike',
  'dashboard.contests.restriction_geographic_desc': 'Geographic restriction.',
  'dashboard.contests.report_contestant.reasons.harassment': 'Harassment',
  'dashboard.contests.report_contestant.reasons.copyright': 'Copyright violation',
  'dashboard.contests.report_contestant.error.reason_required': 'Please select a reason',
  'dashboard.contests.report_contestant.error.description_required': 'Description is required',
  'dashboard.contests.report_contestant.error.description_min_length':
    'Description must be at least 10 characters',
  'dashboard.contests.report_contestant.description':
    'Describe the reason for your report. Our team will review your request.',
  'dashboard.contests.report_contestant.success_title': 'Report submitted',
  'dashboard.contests.report_contestant.success':
    'Your report was submitted successfully. Thank you for helping keep the community safe!',
  'dashboard.contests.report_contestant.description_label': 'Detailed description',
  'dashboard.contests.report_contestant.description_placeholder':
    'Describe in detail the reason for your report...',
  'dashboard.contests.report_contestant.min_chars': 'Minimum 10 characters',
  'dashboard.affiliates.send_invitation': 'Send invitation',
  'dashboard.affiliates.invite_email_required': 'Email is required',
  'dashboard.commissions.subtitle': 'Track your earnings and affiliate revenue',
  'dashboard.feed.create_post_placeholder': "What's on your mind?",
  'admin.dashboard.periods.today': 'Today',
  'admin.contestants.registration_date': 'Registration date',
  'admin.transactions.type.entry_fee': 'Entry fee',
  'admin.contests.error_description_required': 'Description is required',
  'verification.description_required': 'Description is required',
  'verification.proof_image': 'Proof image (screenshot)',
  'verification.camera_error': 'Unable to access the camera',
  'verification.microphone_error': 'Unable to access the microphone',
  'profile_setup.avatar_required': 'Profile photo is required',
  'profile_setup.date_of_birth': 'Date of birth',
  'payment.instructions_description': 'Follow the instructions below to complete your payment.',
  'payment.pay_for_others': 'Or pay for others',
  'payment.username_or_email': 'Username or email',
}

function setKey(obj, key, val) {
  const parts = key.split('.')
  let cur = obj
  for (let i = 0; i < parts.length - 1; i++) {
    if (!cur[parts[i]] || typeof cur[parts[i]] !== 'object') cur[parts[i]] = {}
    cur = cur[parts[i]]
  }
  cur[parts[parts.length - 1]] = val
}

const en = JSON.parse(fs.readFileSync(EN_PATH, 'utf8'))
for (const [key, val] of Object.entries(FIXES)) {
  setKey(en, key, val)
}
fs.writeFileSync(EN_PATH, JSON.stringify(en, null, 2) + '\n')
console.log('Fixed', Object.keys(FIXES).length, 'en.json entries')
