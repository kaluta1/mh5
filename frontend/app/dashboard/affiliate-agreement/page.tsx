'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/use-auth'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { FileText, CheckCircle2, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import Link from 'next/link'

export default function AffiliateAgreementPage() {
  const { user, isAuthenticated, isLoading } = useAuth()
  const { t } = useLanguage()
  const router = useRouter()
  const { addToast } = useToast()
  
  const [hasAccepted, setHasAccepted] = useState(false)
  const [isChecked, setIsChecked] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [pageLoading, setPageLoading] = useState(true)
  const [successMessage, setSuccessMessage] = useState('')

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    } else if (!isLoading && isAuthenticated) {
      checkAgreementStatus()
    }
  }, [isAuthenticated, isLoading, router])

  // Check if agreement was just accepted
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    if (urlParams.get('accepted') === '1') {
      setHasAccepted(true)
      setSuccessMessage('You have successfully accepted the Affiliate Agreement.')
    }
  }, [])

  const checkAgreementStatus = async () => {
    try {
      const token = localStorage.getItem('access_token')
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {}
      
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/user/me`, {
        headers
      })
      
      if (response.ok) {
        const userData = await response.json()
        // Assuming the API returns affiliate_agreement_accepted field
        setHasAccepted(userData.affiliate_agreement_accepted || false)
      }
    } catch (error) {
      console.error('Error checking agreement status:', error)
    } finally {
      setPageLoading(false)
    }
  }

  const acceptAgreement = async () => {
    if (!isChecked) return

    setIsSubmitting(true)
    try {
      const token = localStorage.getItem('access_token')
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/affiliates/accept-agreement`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ accepted: true })
      })

      if (response.ok) {
        setHasAccepted(true)
        setSuccessMessage('You have successfully accepted the Affiliate Agreement.')
        addToast('Agreement accepted successfully', 'success')
        // Update URL without reload
        router.push('/dashboard/affiliate-agreement?accepted=1', { scroll: false })
      } else {
        const errorData = await response.json()
        addToast(errorData.detail || 'Error accepting agreement', 'error')
      }
    } catch (error) {
      console.error('Error accepting agreement:', error)
      addToast('An error occurred. Please try again.', 'error')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading || pageLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-48 bg-gray-200 dark:bg-gray-700 rounded-lg" />
        <div className="h-96 bg-gray-200 dark:bg-gray-700 rounded-2xl" />
      </div>
    )
  }

  if (!isAuthenticated || !user) {
    return null
  }

  return (
    <div className="space-y-6 pb-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-myfav-primary flex items-center justify-center shadow-lg shadow-myfav-primary/25">
            <FileText className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">
              AFFILIATE AGREEMENT
            </h1>
            {hasAccepted && (
              <span className="inline-flex items-center gap-1 px-3 py-1 mt-2 text-sm font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full">
                <CheckCircle2 className="w-4 h-4" />
                Already Accepted
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Agreement Content */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm overflow-hidden">
        <div className="p-6 sm:p-8 space-y-6">
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <p className="text-gray-700 dark:text-gray-300">
              This Affiliate Agreement ("Agreement") is entered into between Kaluta Shopping Mall Inc., a company duly incorporated under the laws of Canada, doing business as Digital Shopping Mall ("Company", "we", "our", or "us"), and you ("Affiliate", "you", or "your") upon your acceptance of the terms and conditions herein.
            </p>
            
            <p className="text-gray-700 dark:text-gray-300">
              By accepting this Agreement, you acknowledge that you have read, understood, and agreed to be bound by the terms below, and that you are legally authorized to act on behalf of yourself or your organization.
            </p>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">1. Enrollment in the Affiliate Program</h5>
            <p className="text-gray-700 dark:text-gray-300">To become an Affiliate, you must:</p>
            <ol type="a" className="list-decimal list-inside space-y-2 text-gray-700 dark:text-gray-300 ml-4">
              <li>Submit an application via our website or through an invitation link;</li>
              <li>Read and agree to this Agreement; and</li>
              <li>Be approved by us. Approval is at our sole discretion.</li>
            </ol>
            <p className="text-gray-700 dark:text-gray-300 mt-3">
              We reserve the right to refuse participation to any applicant for any reason, including but not limited to concerns about legal compliance, previous conduct, or reputational risks.
            </p>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">2. Eligibility</h5>
            <p className="text-gray-700 dark:text-gray-300">To participate in our Affiliate Program, you must:</p>
            <ul className="list-disc list-inside space-y-2 text-gray-700 dark:text-gray-300 ml-4">
              <li>Be at least 18 years old or the age of majority in your province or territory;</li>
              <li>Reside in a country where participation in affiliate programs is legal;</li>
              <li>Provide accurate identification and tax information, as required under Canadian law.</li>
            </ul>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">3. Affiliate Responsibilities</h5>
            <p className="text-gray-700 dark:text-gray-300">As an Affiliate, you agree to:</p>
            <ul className="list-disc list-inside space-y-2 text-gray-700 dark:text-gray-300 ml-4">
              <li>Promote our platform ethically and truthfully;</li>
              <li>Not make false or misleading statements regarding our products, services, or earnings potential;</li>
              <li>Comply with all applicable federal, provincial, and local laws including, but not limited to, the Competition Act, Privacy Act, and CASL (Canada's Anti-Spam Legislation);</li>
              <li>Avoid spamming, click fraud, or deceptive advertising practices;</li>
              <li>Ensure that all your marketing materials disclose your affiliate relationship with us, in compliance with Canadian advertising guidelines and industry standards.</li>
            </ul>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">4. Commission Structure</h5>
            <p className="text-gray-700 dark:text-gray-300">
              You will be eligible to earn commissions as outlined in our Affiliate Commission Plan, which may include multiple levels (up to 10 generations) based on tracked purchases made by referred users.
            </p>
            <p className="text-gray-700 dark:text-gray-300">All commissions:</p>
            <ul className="list-disc list-inside space-y-2 text-gray-700 dark:text-gray-300 ml-4">
              <li>Will be calculated only after a purchase is confirmed and completed;</li>
              <li>Will be paid monthly, subject to a minimum payout threshold;</li>
              <li>May be forfeited in case of fraudulent activity, policy violations, or returned/cancelled orders.</li>
            </ul>
            <p className="text-gray-700 dark:text-gray-300 mt-3">
              We reserve the right to amend the commission structure at any time with at least 30 days' notice to active affiliates.
            </p>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">5. Tracking and Attribution</h5>
            <ul className="list-disc list-inside space-y-2 text-gray-700 dark:text-gray-300 ml-4">
              <li>Affiliate tracking is performed using industry-standard methods, including cookies and tracking links;</li>
              <li>Referral attribution will be maintained for 30 days from the last click;</li>
              <li>In case of multiple affiliates referring the same customer, commission will be awarded to the last referring affiliate before purchase.</li>
            </ul>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">6. Payment Terms</h5>
            <p className="text-gray-700 dark:text-gray-300">Commissions will be paid according to the following terms:</p>
            <ul className="list-disc list-inside space-y-2 text-gray-700 dark:text-gray-300 ml-4">
              <li>Payments will be processed monthly for the previous month's confirmed commissions;</li>
              <li>A minimum threshold of $50 CAD must be reached before payment is issued;</li>
              <li>Payment methods include direct deposit (for Canadian affiliates), PayPal, or cryptocurrency;</li>
              <li>All applicable taxes are the responsibility of the Affiliate.</li>
            </ul>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">7. Term and Termination</h5>
            <p className="text-gray-700 dark:text-gray-300">This Agreement:</p>
            <ul className="list-disc list-inside space-y-2 text-gray-700 dark:text-gray-300 ml-4">
              <li>Commences upon your acceptance and our approval;</li>
              <li>Continues until terminated by either party;</li>
              <li>May be terminated by either party with 30 days' written notice;</li>
              <li>May be terminated immediately by us in case of violation of this Agreement or applicable laws.</li>
            </ul>
            <p className="text-gray-700 dark:text-gray-300 mt-3">
              Upon termination, all rights to future commissions shall cease, except for commissions already earned but not yet paid.
            </p>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">8. Intellectual Property</h5>
            <p className="text-gray-700 dark:text-gray-300">You acknowledge that:</p>
            <ul className="list-disc list-inside space-y-2 text-gray-700 dark:text-gray-300 ml-4">
              <li>All trademarks, logos, and marketing materials provided to you remain our exclusive property;</li>
              <li>Your use of our intellectual property is limited to promoting our platform as permitted under this Agreement;</li>
              <li>Any unauthorized use of our intellectual property may result in immediate termination and legal action.</li>
            </ul>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">9. Confidentiality</h5>
            <p className="text-gray-700 dark:text-gray-300">
              You agree to maintain the confidentiality of any non-public information disclosed to you, including but not limited to commission structures, marketing strategies, and customer data.
            </p>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">10. Limitation of Liability</h5>
            <p className="text-gray-700 dark:text-gray-300">
              To the maximum extent permitted by law, we shall not be liable for any indirect, incidental, special, consequential, or punitive damages, including lost profits, arising out of or relating to this Agreement.
            </p>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">11. Indemnification</h5>
            <p className="text-gray-700 dark:text-gray-300">
              You agree to indemnify and hold harmless the Company, its officers, directors, employees, and agents from any claims, damages, liabilities, costs, or expenses arising from your breach of this Agreement or your promotional activities.
            </p>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">12. Governing Law</h5>
            <p className="text-gray-700 dark:text-gray-300">
              This Agreement shall be governed by and construed in accordance with the laws of the Province of Ontario, Canada, without regard to its conflict of law principles.
            </p>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">13. Entire Agreement</h5>
            <p className="text-gray-700 dark:text-gray-300">
              This Agreement constitutes the entire agreement between the parties concerning the Affiliate Program and supersedes all prior agreements, communications, or understandings.
            </p>
            
            <h5 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-3">14. Electronic Consent</h5>
            <p className="text-gray-700 dark:text-gray-300">
              By checking the box labeled "I Agree" or signing digitally, you affirm that you have read and accepted this Affiliate Agreement and that it is legally binding upon you.
            </p>
            
            <p className="text-center mt-8 text-gray-700 dark:text-gray-300 font-medium">
              IN WITNESS WHEREOF, you agree to these terms effective as of the date of your acceptance.
            </p>
          </div>
        </div>
      </div>

      {/* Acceptance Section */}
      {!hasAccepted ? (
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm p-6">
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <input
                type="checkbox"
                id="agreement-checkbox"
                checked={isChecked}
                onChange={(e) => setIsChecked(e.target.checked)}
                className="mt-1 w-5 h-5 rounded border-gray-300 text-myfav-primary focus:ring-myfav-primary focus:ring-2"
              />
              <label htmlFor="agreement-checkbox" className="text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                I have read and agree to the terms and conditions of the Affiliate Agreement
              </label>
            </div>
            
            <Button
              onClick={acceptAgreement}
              disabled={!isChecked || isSubmitting}
              className="w-full sm:w-auto bg-myfav-primary hover:bg-myfav-primary/90 text-white rounded-xl shadow-lg shadow-myfav-primary/25 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4 mr-2" />
                  Accept Agreement
                </>
              )}
            </Button>
          </div>
        </div>
      ) : (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-2xl p-6">
          <div className="flex items-center gap-3 text-green-700 dark:text-green-400">
            <CheckCircle2 className="w-5 h-5" />
            <p className="font-medium">
              {successMessage || "You have already accepted this affiliate agreement."}
            </p>
          </div>
          <div className="mt-4">
            <Link href="/dashboard">
              <Button variant="outline" className="rounded-xl">
                Return to Dashboard
              </Button>
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

