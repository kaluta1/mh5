// @ts-nocheck
export type Language = 'en' | 'fr' | 'es' | 'de'

export interface LanguageInfo {
  name: string
  flag: string
}

export const languages: Record<Language, LanguageInfo> = {
  fr: { name: 'Français', flag: '🇫🇷' },
  en: { name: 'English', flag: '🇬🇧' },
  es: { name: 'Español', flag: '🇪🇸' },
  de: { name: 'Deutsch', flag: '🇩🇪' }
}

export const maintenanceTranslations = {
  en: {
    maintenance: {
      title: "We'll be back soon",
      message: "We are refining our contest migration functionality and adding more features to enhance user experience. We will be back soon.",
      backSoon: "Back soon"
    }
  },
  fr: {
    maintenance: {
      title: "Nous revenons bientôt",
      message: "Nous peaufinons notre fonctionnalité de migration de concours et ajoutons plus de fonctionnalités pour améliorer l'expérience utilisateur. Nous serons de retour bientôt.",
      backSoon: "De retour bientôt"
    }
  },
  es: {
    maintenance: {
      title: "Volveremos pronto",
      message: "Estamos perfeccionando nuestra funcionalidad de migración de concursos y agregando más características para mejorar la experiencia del usuario. Volveremos pronto.",
      backSoon: "Volveremos pronto"
    }
  },
  de: {
    maintenance: {
      title: "Wir sind bald zurück",
      message: "Wir verfeinern unsere Wettbewerbsmigrationsfunktion und fügen weitere Funktionen hinzu, um die Benutzererfahrung zu verbessern. Wir sind bald wieder zurück.",
      backSoon: "Bald zurück"
    }
  }
}

export interface TranslationKeys {
  maintenance: {
    title: string
    message: string
    backSoon: string
  }
  hero: {
    badge: string
    title_line1: string
    title_line2: string
    title_line3: string
    subtitle: string
    cta: string
    demo: string
    stats: {
      participants: string
      contests: string
      countries: string
    }
    trust: {
      secure: string
      support: string
      free: string
    }
  }
  nav: {
    home: string
    contests: string
    rankings: string
    community: string
    about: string
    login: string
    register: string
  }
  navigation: {
    home: string
    landing: string
    dashboard: string
    contests: string
    clubs: string
    about: string
    contact: string
    login: string
    register: string
    download_app: string
  }
  header: {
    language: string
    theme: string
  }
  auth: {
    email: string
    password: string
    username: string
    forgotPassword: string
    loginError: string
    registerError: string
    referral_detected: string
    referral_code: string
    referral_bonus: string
    login: {
      title: string
      subtitle: string
      email_placeholder: string
      password_placeholder: string
      forgot_password: string
      loading: string
      submit: string
      no_account: string
      register_link: string
      errors: {
        required_fields: string
        invalid_credentials: string
        timeout?: string
        network_error?: string
        service_unavailable?: string
      }
    }
    register: {
      title: string
      subtitle: string
      email_placeholder: string
      username_placeholder: string
      username_hint: string
      username_no_spaces_warning: string
      username_space_not_allowed: string
      password_placeholder: string
      confirm_password_placeholder: string
      full_name_placeholder: string
      phone_placeholder: string
      referral_code_placeholder: string
      country: string
      country_placeholder: string
      city: string
      city_placeholder: string
      loading: string
      submit: string
      have_account: string
      login_link: string
      terms_accept: string
      errors: {
        required_fields: string
        password_mismatch: string
        password_min_length: string
        terms_required: string
        username_invalid_chars: string
        invalid_email: string
        password_requirements: string
      }
      password_requirements_title: string
      password_requirement_length: string
      password_requirement_uppercase: string
      password_requirement_lowercase: string
      password_requirement_number: string
      password_requirement_special: string
    }
    verify_email: {
      no_token: string
      success: string
      error: string
      verifying: string
      please_wait: string
      success_title: string
      redirecting: string
      error_title: string
      invalid_token: string
    }
    forgot_password: {
      title: string
      description: string
      email_required: string
      send_reset_link: string
      success: string
      success_title: string
      success_message: string
      check_spam: string
      remember_password: string
      error: string
    }
    reset_password: {
      title: string
      description: string
      no_token: string
      password_required: string
      password_min_length: string
      confirm_password_required: string
      passwords_not_match: string
      new_password: string
      confirm_password: string
      submit: string
      success: string
      success_title: string
      success_message: string
      redirecting: string
      error: string
      invalid_token: string
    }
  }
  not_found: {
    title: string
    description: string
    go_back: string
    go_home: string
    quick_links: string
    help_text: string
  }
  common: {
    loading: string
    error: string
    success: string
    cancel: string
    confirm: string
    continue: string
    or: string
    redirecting: string
    please_wait: string
    back: string
    back_to_dashboard: string
    previous: string
    next: string
    submitting: string
    no_documents: string
    profile_setup: string
    profile_setup_description: string
    edit: string
    delete: string
    deleting: string
    confirm_delete: string
    deleted_successfully: string
    likes: string
    comments: string
    search: string
    clear: string
    welcome: string
    access_denied: string
    no_permission: string
    refresh: string
    network_error: string
    optional: string
    save: string
    unknown: string
    load_more: string
    actions: string
  }
  settings: {
    title: string
    description: string
    profile: string
    location: string
    demographics: string
    continent: string
    region: string
    country: string
    city: string
    current_location: string
    location_locked_title: string
    location_locked_message: string
    save: string
    remove: string
    profile_completion: string
    missing: string
    referral_code_label: string
    admin: string
    verified: string
    verify_identity: string
    years: string
    user: string
    profile_photo: string
    biography: string
    password: {
      title: string
      description: string
      current: string
      new: string
      confirm: string
      current_required: string
      new_required: string
      confirm_required: string
      min_length: string
      mismatch: string
      same_password: string
      session_expired: string
      success: string
      error: string
      saving: string
      save: string
      security_info: string
      security_description: string
      min_6_chars: string
      uppercase: string
      lowercase: string
      number: string
    }
    password_short: string
  }
  profile_setup: {
    location: string
    gender: string
    date_of_birth: string
    male: string
    female: string
    other: string
    prefer_not_to_say: string
    first_name: string
    first_name_placeholder: string
    first_name_required: string
    last_name: string
    last_name_placeholder: string
    last_name_required: string
    avatar: string
    avatar_required: string
    bio: string
    bio_placeholder: string
    bio_required: string
    characters: string
    city_required: string
    continent_required: string
    region_required: string
    country_required: string
    gender_required: string
    dob_required: string
    session_expired: string
    update_error: string
    success: string
    continue: string
    info: string
    click_upload: string
    preparing: string
    checking_files: string
    uploading: string
    images: string
    upload_error: string
  }
  participation: {
    location: string
    category: string
    categoryPlaceholder: string
    title: string
    title_placeholder: string
    description: string
    descriptionPlaceholder: string
    characters: string
    media: string
    images: string
    images_placeholder: string
    video: string
    video_placeholder: string
    video_optional: string
    clickUpload: string
    preparing: string
    checkingFiles: string
    uploading: string
    imagesVideos: string
    uploadError: string
    uploadedFiles: string
    submit: string
    cancel: string
    profile_incomplete_title: string
    profile_incomplete_message: string
    complete_profile_button: string
    kyc_notification: string
    or: string
    add_by_url: string
    add_video_by_url: string
    add: string
    image_url_placeholder: string
    video_url_placeholder: string
    invalid_video_url: string
    video_platform_not_allowed: string
    video_file_not_allowed: string
    youtube_shorts_not_allowed: string
    tiktok_preview_unavailable: string
    watch_on_tiktok: string
    url_required: string
    invalid_url: string
    max_images_reached: string
    image_added: string
    video_added: string
    media_requirements: string
    images_required: string
    video_required: string
    video_required_title: string
    content_title: string
    content_title_placeholder: string
    content_description: string
    content_description_placeholder: string
    content_image: string
    content_video_required: string
    content_video_optional: string
    min_characters: string
    important_errors: string
    // Nominator location fields
    nominator_location: string
    nominator_location_description: string
    nominator_country: string
    select_country: string
    nominator_country_note: string
    nominator_city: string
    nominator_city_placeholder: string
    select_city: string
    select_country_first: string
    ad_revenue_warning: string
    // Stepper
    step_info: string
    step_media: string
    step_review: string
    time_remaining: string
    deadline: string
    submission_period_ended: string
    review_title: string
    supported_platforms: string
    unrecognized_video_link: string
    errors: {
      content_title_required: string
      content_title_min_length: string
      content_title_max_length: string
      content_description_required: string
      content_description_min_length: string
      content_description_max_length: string
      content_image_required: string
      at_least_one_image: string
      content_video_required: string
      video_required_for_contest: string
      fill_all_fields: string
      nominator_country_required: string
    }
  }
  features: {
    title: string
    subtitle: string
    items: {
      [key: string]: {
        title: string
        description: string
      }
    }
  }
  testimonials: {
    title: string
    subtitle: string
    cta: string
    users: string
    items: {
      [key: string]: {
        name: string
        text: string
        role: string
        rating: number
        location: string
      }
    }
    favorites: {
      title: string
      description: string
      description_contestants: string
      contests_tab: string
      contestants_tab: string
      no_favorite_contests: string
      no_favorite_contestants: string
      no_favorites_yet: string
      no_favorites_hint: string
      browse_contests: string
    }
  }
  cta: {
    title: string
    subtitle: string
    button: string
    features: {
      instant: string
      global: string
      secure: string
      free_contests: string
      active_community: string
      real_rewards: string
    }
    trust: {
      instant: string
      secure: string
      support: string
    }
  }
  footer: {
    description: string
    copyright: string
    newsletter: {
      title: string
      subtitle: string
      placeholder: string
      subscribe: string
      terms: string
    }
    brand: {
      countries: string
      support: string
      email: string
    }
    quick_links: {
      title: string
      about: string
      contests: string
      how_it_works: string
      affiliate: string
      support: string
    }
    categories: {
      title: string
      beauty: string
      handsome: string
      latest_hits: string
      pets: string
      sports_clubs: string
      no_categories: string
    }
    legal: {
      title: string
      privacy: string
      terms: string
      cookies: string
      gdpr: string
    }
  }
  contestant_detail: {
    about: string
    gallery: string
    photos: string
    videos: string
    contest_info: string
    candidate_info: string
    title: string
    participants: string
    registered_on: string
    status: string
    qualified: string
    pending: string
    confirm_vote: string
    vote_confirmation: string
    are_you_sure: string
    cancel: string
    vote: string
    voted: string
    voting: string
    cover_image: string
    vote_error: string
    vote_success: string
    add_reaction: string
    react: string
    like: string
    love: string
    wow: string
    dislike: string
    vote_history: string
    no_votes: string
    voted_for: string
    reaction: string
    comment: string
    date: string
    comments: string
    add_comment: string
    comment_placeholder: string
    comment_on_photo: string
    comment_on_video: string
    comment_on_contest: string
    no_comments: string
    comment_posted: string
    comment_error: string
    comments_count: string
    reply: string
    reply_placeholder: string
    like_comment: string
    media_preview: string
    close: string
    of: string
    contestant_label: string
    nominator_label: string
    nominated_for: string
    contest_rank_label: string
    description_section: string
    candidacy_id: string
    season_label: string
    entry_fallback_title: string
    full_description: string
  }
  admin: {
    title: string
    subtitle: string
    nav: {
      main: string
      dashboard: string
      management: string
      seasons: string
      contests: string
      contestants: string
      users: string
      kyc: string
      reports: string
      configuration: string
      categories: string
      commission_settings: string
      suggested_contests: string
      transactions: string
      microservices: string
      accounting: string
    }
    dashboard: {
      total_seasons: string
      active: string
      inactive: string
      admins: string
      votes: string
      total_votes: string
      comments: string
      total_comments: string
      quick_actions: string
      user_progress: string
      reports: {
        title: string
        description: string
        financial_report: string
        financial_description: string
        users_report: string
        users_description: string
        contests_report: string
        contests_description: string
        votes_report: string
        votes_description: string
        recent_reports: string
      }
      chart_labels: {
        total_users: string
        active_users: string
        new_users: string
      }
      periods: {
        today: string
        yesterday: string
        week: string
        month: string
        year: string
      }
      statistics: {
        total_deposits: string
        total_withdrawals: string
        verified_users: string
        reports: string
        categories: string
        deposits_chart: string
        withdrawals_chart: string
        categories_chart: string
        reports_by_type: string
        amount_eur: string
        deposits_count: string
        withdrawals_count: string
        kyc_verified: string
        reports_count: string
        categories_total: string
        amount: string
        count: string
        contests: string
        uses: string
        period: string
        custom: string
        apply: string
        loading: string
        refresh: string
        no_data_available: string
      }
      profile: {
        participations: string
        total_votes: string
        total_favorites: string
        followers: string
        following: string
        contestants: string
        all_rounds: string
        no_entries: string
        verified: string
        years: string
        follow: string
        unfollow: string
        followed: string
        unfollowed: string
      }
    }
    rounds: {
      title: string
      description: string
      new_round: string
      edit: string
      create: string
      contest: string
      select_contest: string
      name: string
      status: string
      load_error: string
      delete_success: string
      delete_error: string
      update_success: string
      create_success: string
      search: string
      confirm_delete: string
      delete_warning: string
      // Season dates labels
      city_season: string
      country_season: string
      regional_season: string
      continental_season: string
      global_season: string
      start_date: string
      end_date: string
    }
    seasons: {
      title: string
      description: string
      new_season: string
      edit_season: string
      create_season: string
      year: string
      season_number: string
      season_title: string
      status: string
      start_date: string
      end_date: string
      upload_end_date: string
      upcoming: string
      upload_phase: string
      voting_active: string
      voting_ended: string
      completed: string
      cancelled: string
      edit: string
      delete: string
      cancel: string
      create: string
      confirm_delete: string
      confirm_delete_title: string
      confirm_delete_message: string
      no_seasons: string
      create_success: string
      update_success: string
      delete_success: string
      load_error: string
      save_error: string
      delete_error: string
      level: string
      level_city: string
      level_country: string
      filter_level: string
      level_regional: string
      level_continent: string
      level_global: string
      level_placeholder: string
      season_title_placeholder: string
      error_level_exists: string
      error_invalid_level: string
      contestants_count: string
      contests_count: string
    }
    contests: {
      title: string
      tab_contests: string
      tab_rounds: string
      description: string
      new_contest: string
      edit_contest: string
      create_contest: string
      name: string
      contest_description: string
      contest_type: string
      level: string
      city: string
      country: string
      region: string
      continent: string
      global: string
      active: string
      inactive: string
      upload_open: string
      voting_active: string
      edit: string
      delete: string
      cancel: string
      confirm_delete: string
      image: string
      no_contests: string
      voting_restriction: string
      none: string
      male_only: string
      female_only: string
      geographic: string
      age_restricted: string
      start_date: string
      end_date: string
      search_placeholder: string
      sort: string
      create_success: string
      create_error: string
      update_success: string
      update_error: string
      delete_success: string
      delete_error: string
      sort_date: string
      sort_name: string
      sort_status: string
      participant_count: string
      creating: string
      updating: string
      candidates: string
      confirm_delete_title: string
      confirm_delete_message: string
      submission_start: string
      submission_end: string
      voting_start: string
      voting_end: string
      season: string
      select_season: string
      delete_warning: string
      contest_dates: string
      approved: string
      rejected: string
      filter: string
      approve: string
      reject: string
      view: string
      no_kyc: string
      verification_score: string
      identity: string
      document: string
      address: string
      face: string
      confidence_score: string
      rejection_reason: string
      // Voting type translations
      voting_type: string
      select_voting_type: string
      new_voting_type: string
      voting_types_load_error: string
      voting_type_created: string
      voting_type_create_error: string
      create_voting_type: string
      voting_type_name_placeholder: string
      voting_level: string
      commission_source: string
      commission_rules: string
      commission_rules_help: string
      commission_advert: string
      commission_affiliate: string
      commission_kyc: string
      commission_mfm: string
      create: string
      // Category translations
      category: string
      select_category: string
      no_category: string
      add_category: string
      create_category: string
      category_name_required: string
      category_created: string
      category_create_error: string
      categories_load_error: string
      category_name_placeholder: string
      slug: string
      slug_placeholder: string
      slug_help: string
      category_description_placeholder: string
      contest_type_auto_filled: string
      verification_requirements: string
      media_requirements: string
      participant_individual: string
      participant_pet: string
      participant_club: string
      verification_video_max_duration: string

      verification_max_size_mb: string
      new_participation: string
      new_nomination: string
      min_images: string
      max_images: string
      min_age: string
      max_age: string
      max_videos: string
      video_max_duration: string
      video_max_size_mb: string
      requires_video: string
      kyc_required: string
      verification_visual: string
      verification_voice: string
      verification_brand: string
      verification_content: string
    }
    contestants: {
      title: string
      description: string
      search_placeholder: string
      all: string
      pending: string
      verified: string
      filter: string
      approve: string
      reject: string
      view: string
      author: string
      images: string
      videos: string
      votes: string
      comments: string
      status: string
      registration_date: string
      actions: string
      contestant_details: string
      close: string
      no_contestants: string
      status_pending: string
      status_verified: string
      status_rejected: string
      approve_success: string
      approve_error: string
      reject_success: string
      reject_error: string
      status_update_success: string
      status_update_error: string
      comment_delete_success: string
      comment_delete_error: string
      comment_hide_success: string
      comment_hide_error: string
      comment_show_success: string
      comment_show_error: string
      comment_restore_success: string
      comment_restore_error: string
      new_contestant: string
      edit_contestant: string
      user: string
      select_user: string
      select_season: string
      no_seasons_for_level: string
      title_placeholder: string
      description_placeholder: string
      create_success: string
      update_success: string
      save_error: string
      seasons_load_error: string
      no_seasons_available: string
    }
    kyc: {
      title: string
      description: string
      search_placeholder: string
      pending: string
      approved: string
      rejected: string
      filter: string
      approve: string
      reject: string
      view: string
      no_kyc: string
      verification_score: string
      identity: string
      document: string
      address: string
      face: string
      confidence_score: string
      rejection_reason: string
    }
    reports: {
      title: string
      description: string
      search_placeholder: string
      all: string
      pending: string
      reviewed: string
      resolved: string
      no_reports: string
      no_reports_found: string
      report_number: string
      reason: string
      description_label: string
      status: string
      details: string
      reported_contestant: string
      contestant_author: string
      reporter: string
      contest: string
      created_at: string
      reviewed_at: string
      moderator_notes: string
      verification_status: string
      verification_status_pending: string
      verification_status_approved: string
      verification_status_rejected: string
      reason_spam: string
      reason_inappropriate: string
      reason_harassment: string
      reason_fake: string
      reason_copyright: string
      reason_other: string
      no_title: string
      load_error: string
      report_details: string
      report_details_description: string
      reason_label: string
    }
    transactions: {
      title: string
      description: string
      search_placeholder: string
      all_types: string
      all_statuses: string
      no_transactions: string
      no_transactions_found: string
      transaction: string
      transaction_details: string
      transaction_details_description: string
      type: {
        deposit: string
        withdrawal: string
        entry_fee: string
        prize_payout: string
        commission: string
        refund: string
      }
      status: {
        pending: string
        completed: string
        failed: string
        cancelled: string
      }
      user: string
      contest: string
      payment_method: string
      product_type: string
      amount: string
      currency: string
      description: string
      reference: string
      order_id: string
      external_payment_id: string
      tx_hash: string
      created_at: string
      processed_at: string
      validated_at: string
      type_label: string
      status_label: string
      details: string
      search: string
      load_error: string
    }
    accounting: {
      title: string
      subtitle: string
      refresh: string
      total_revenue: string
      ytd: string
      journal_tab: string
      coa_tab: string
      journal_title: string
      journal_desc: string
      coa_title: string
      coa_desc: string
      table: {
        date: string
        ref: string
        description: string
        debit: string
        credit: string
        status: string
        code: string
        account: string
        type: string
        balance: string
      }
      error_loading: string
      retry: string
      no_journal: string
      no_coa: string
    }
    commission_settings: {
      subtitle: string
      coming_soon: string
    }
    microservices: {
      subtitle: string
      coming_soon: string
    }
    users: {
      title: string
      description: string
      search_placeholder: string
      all: string
      admins: string
      verified: string
      inactive: string
      filter: string
      table_user: string
      table_email: string
      table_participations: string
      table_prizes: string
      table_candidates: string
      table_contests: string
      table_status: string
      table_actions: string
      make_admin: string
      remove_admin: string
      activate: string
      deactivate: string
      no_users: string
      registered: string
      inactive_status: string
      user: string
      email: string
      participations: string
      prizes: string
      candidates: string
      contests: string
      status: string
      actions: string
      details: string
      comments: string
      view_comments: string
      no_comments: string
      comment_text: string
      comment_date: string
      comment_author: string
      city: string
      country: string
      continent: string
      region: string
      kyc_status: string
      kyc_verified: string
      kyc_pending: string
      date_of_birth: string
      phone: string
      bio: string
      last_login: string
      joined: string
      participations_count: string
      prizes_count: string
      contestants_count: string
      contests_participated: string
      confirm_delete_title: string
      confirm_delete_message: string
      delete: string
      cancel: string
      delete_success: string
      delete_error: string
      personal_info: string
      account_status: string
      verify_kyc: string
      unverify_kyc: string
      kyc_verify_success: string
      kyc_unverify_success: string
      toggle_admin_success: string
      toggle_admin_error: string
      toggle_active_success_deactivate: string
      toggle_active_success_activate: string
      toggle_active_error: string
      load_error: string
      load_details_error: string
      edit_comment: string
      delete_comment: string
      hide_comment: string
      show_comment: string
      comment_edit_success: string
      comment_delete_success: string
      comment_hide_success: string
      comment_show_success: string
      comment_edit_error: string
      comment_delete_error: string
      comment_hide_error: string
      comment_show_error: string
      contest_label: string
      contestant_label: string
    }
    reports: {
      title: string
      description: string
      pending: string
      reviewed: string
      resolved: string
      search_placeholder: string
      filter: string
      all: string
      no_reports: string
      reporter: string
      reported_content: string
      reason: string
      status: string
      date: string
      actions: string
      view: string
      mark_reviewed: string
      mark_resolved: string
      details: string
      close: string
      report_details: string
      reported_by: string
      reported_at: string
      report_reason: string
      report_description: string
      report_status: string
      moderator_notes: string
      reviewed_by: string
      reviewed_at: string
      content_type: string
      contestant: string
      comment: string
      media: string
      user: string
      mark_reviewed_success: string
      mark_reviewed_error: string
      mark_resolved_success: string
      mark_resolved_error: string
      load_error: string
    }
    dashboard: {
      welcome: string
      subtitle: string
      search: {
        placeholder: string
        title: string
        description: string
        no_results: string
        start_typing: string
        contest: string
        contestant: string
        club: string
        product: string
        recent_searches?: string
        no_history?: string
      }
      nav: {
        home: string
        contests: string
        my_applications: string
        clubs: string
        favorites: string
        search: string
        pages: string
        wallet: string
        affiliates: string
        commissions: string
        leaderboard: string
        prize: string
        shop: string
        main: string
        competitions: string
        business: string
        resources: string
        founding_member: string
        affiliate_program: string
        affiliate_agreement: string
        account: string
        settings: string
        admin: string
        admin_panel: string
        admin_panel_desc: string
        notifications?: string
        notifications_desc?: string
        home_desc?: string
        search_desc?: string
        contests_desc?: string
        my_applications_desc?: string
        clubs_desc?: string
        favorites_desc?: string
        wallet_desc?: string
        affiliates_desc?: string
        commissions_desc?: string
        prize_desc?: string
        messages?: string
        following?: string
        social?: string
      }
      feed?: {
        welcome: string
        welcome_description: string
        create_first_post: string
        loading: string
        load_more: string
        create_post: string
        delete_confirm: string
      }
      messages?: {
        title: string
        subtitle: string
        no_conversations: string
        start_conversation: string
        encrypted_message: string
        end_to_end_encrypted: string
        type_message: string
        select_conversation: string
        select_conversation_desc: string
      }
      groups?: {
        title: string
        subtitle: string
        search_placeholder: string
        no_groups_found: string
        no_groups_available: string
        try_keywords: string
        be_first: string
        create_group: string
        members: string
        created_by: string
        leave: string
        join: string
        create_new_group: string
        group_name: string
        group_name_placeholder: string
        description: string
        description_placeholder: string
        group_type: string
        public: string
        private: string
        cancel: string
        creating: string
        create_group_button: string
      }
      following?: {
        title: string
        subtitle: string
        following_tab: string
        followers_tab: string
        suggested_tab: string
        search_placeholder: string
        no_users_found: string
        no_users: string
        followers: string
        posts: string
        unfollow: string
        follow: string
      }
      leaderboard?: {
        title: string
        subtitle: string
        mfm_subtitle?: string
        regular_tab?: string
        mfm_tab?: string
        referrals: string
        benefit?: string
        champion: string
        no_data: string
        info_title: string
        info_description: string
      }
      stats: {
        contests: string
        clubs: string
        favorites: string
        points: string
      }
      quick_actions: string
      recent_activity: string
      no_activity: string
      position: {
        title: string
        no_contests: string
        rank: string
        points: string
        contests: string
        clubs: string
        affiliates: string
        status: string
        members: string
        referrals: string
        commissions: string
        active: string
      }
      contests: {
        title: string
        description: string
        no_contests: string
        no_description: string
        all: string
        nomination: string
        participations: string
        filter_level: string
        level_city: string
        level_country: string
        all_levels: string
        nominate: string
        edit_nomination: string
        edit_participation: string
        edit: string
        tooltip_nominate: string
        time_remaining_to_nominate: string
        search_placeholder: string
        sort: string
        sort_participants: string
        sort_votes: string
        sort_date: string
        sort_name: string
        voting_type: string
        voting_level_country: string
        voting_level_city: string
        voting_level_regional: string
        voting_level_continent: string
        voting_level_global: string
        status: string
        level: string
        city: string
        country: string
        continental: string
        regional: string
        global: string
        contestants: string
        likes: string
        comments: string
        received: string
        participate: string
        nominate: string
        tooltip_nominate: string
        time_remaining_to_nominate: string
        contest_type: {
          [key: string]: string
        }
        add_favorite: string
        remove_favorite: string
        added_to_favorites: string
        removed_from_favorites: string
        open: string
        open_for_candidacy: string
        closed: string
        max_favorites: string
        favorite_limit_reached: string
        top_participants: string
        top_5_description: string
        view: string
        contestant: string
        view_contestants: string
        view_all_contestants: string
        top_contestants: string
        view_contestants_count: string
        view_contestants_empty: string
        view_contestants_description: string
        time_remaining: string
        time_remaining_to_participate: string
        time_unit_days: string
        time_unit_hours: string
        time_unit_minutes: string
        time_unit_seconds: string
        candidacy_ends: string
        participation_ongoing: string
        vote: string
        view_details: string
        already_voted: string
        already_voted_message: string
        cannot_vote: string
        owner_cannot_vote: string
        own_cannot_vote: string
        votes: string
        contest_info: string
        contest_dates: string
        submission_start: string
        submission_end: string
        voting_start: string
        participant_type: string
        participant_individual: string
        participant_pet: string
        participant_club: string
        participant_content: string
        kyc_required_description: string
        visual_verification_description: string
        voice_verification_description: string
        brand_verification_description: string
        content_verification_description: string
        gender_restriction: string
        gender_restriction_female_description: string
        gender_restriction_male_description: string
        age_restriction: string
        age_restriction_description: string
        submission: string
        voting: string
        start: string
        end: string
        add_to_favorites: string
        remove_from_favorites: string
        reaction_added: string
        reaction_removed: string
        no_reactions: string
        no_votes: string
        no_favorites: string
        more: string
        loading: string
        votes: string
        favorites: string
        points: string
        share: string
        share_title: string
        share_description: string
        share_link_label: string
        copy: string
        copied: string
        share_natively: string
        report: string
        reactions: string
        you_reacted: string
        no_reactions: string
        people_reacted: string
        be_first_to_react: string
        participant: string
        rank: string
        reaction: string
        search_contestant: string
        filtered_by_country: string
        no_contestants: string
        no_contestants_found: string
        like: string
        love: string
        wow: string
        dislike: string
        reply: string
        reply_placeholder: string
        show_replies: string
        hide_replies: string
        like_added: string
        like_removed: string
        comment_added: string
        reply_added: string
        mention_hint: string
        you: string
        favorite: string
        comments_description: string
        vote_error: string
        voting_not_open: string
        already_voted_error: string
        cannot_vote_own: string
        vote_success: string
        vote_replaced: string
        my_votes: string
        no_votes_yet: string
        replace_vote_title: string
        replace_vote_message: string
        replace_vote_position: string
        replace_vote_confirm: string
        max_votes_reached: string
        empty_slot: string
        votes_remaining: string
        drag_to_reorder: string
        vote_gender_restriction_male: string
        vote_gender_restriction_female: string
        vote_gender_not_set: string
        add_comment_placeholder: string
        sending: string
        send: string
        no_comments: string
        gender: string
        edit: string
        delete: string
        age: string
        years: string
        country: string
        city: string
        bio: string
        male: string
        female: string
        my_applications: {
          title: string
          description: string
          no_applications: string
          browse_contests: string
          status: string
          status_pending: string
          status_approved: string
          status_rejected: string
          rank: string
          view_details: string
          view_page: string
          edit_not_available: string
          delete_not_available: string
          delete_confirm_message: string
          details: string
          statistics: string
          total_shares: string
          shares_by_platform: string
          no_shares: string
          contest: string
          date: string
          media: string
          no_title: string
          user: string
          media_alt: string
          video_alt: string
        }
        suggest_contest: {
          title: string
          description: string
          button: string
          name_label: string
          name_placeholder: string
          description_label: string
          description_placeholder: string
          category_label: string
          category_placeholder: string
          submit: string
          submitting: string
          success: string
          success_message: string
          cancel: string
          error: {
            name_required: string
            category_required: string
            submit_error: string
            network_error: string
            server_error: string
          }
        }
        report_contestant: {
          title: string
          description: string
          contestant: string
          reason_label: string
          reason_placeholder: string
          description_label: string
          description_placeholder: string
          characters: string
          submit: string
          submitting: string
          success: string
          cancel: string
          reasons: {
            spam: string
            inappropriate: string
            harassment: string
            fake: string
            copyright: string
            other: string
          }
          error: {
            reason_required: string
            description_required: string
            description_min_length: string
            submit_error: string
            network_error: string
            server_error: string
          }
        }
        participation_form: {
          title: string
          description: string
          edit_title: string
          edit_description: string
          nominate_title: string
          nominate_description: string
          select_media: string
          drag_drop: string
          file_info: string
          submit: string
          success: string
          success_title: string
          success_edit: string
          already_participating: string
          edit_participation: string
          click_add_images: string
          preparing: string
          checking_files: string
          uploading: string
          images_format: string
          click_add_video: string
          video_format: string
          cancel: string
          error: {
            no_media_selected: string
            invalid_file_type: string
            file_too_large: string
            contest_not_found: string
            submit_error: string
            gender_restriction_male: string
            gender_restriction_female: string
            gender_not_set: string
            already_submitted: string
            submission_closed: string
            deadline_passed: string
          }
        }
      }
      favorites: {
        title: string
        description: string
        description_contestants: string
        contests_tab: string
        contestants_tab: string
        no_favorite_contests: string
        no_favorite_contestants: string
        no_favorites_yet: string
        no_favorites_hint: string
        browse_contests: string
      }
    }
  }
  kyc: {
    verification_required: string
    verification_required_description: string
    start_verification: string
    already_verified: string
    already_verified_description: string
    verification_in_progress: string
    verification_in_progress_description: string
    verification_continue_description: string
    continue_verification: string
    login_required: string
    init_error: string
    max_attempts_reached: string
    max_attempts_description: string
    max_attempts_can_pay: string
    buy_attempts: string
    price_per_attempt: string
    pay_and_retry: string
    attempts_remaining: string
    attempts_used: string
    verification_status: string
    verification_status_description: string
    verification_rejected: string
    verification_rejected_description: string
    rejection_reason: string
    submitted_on: string
    submit_again: string
    verification_steps: string
    step_1_title: string
    step_1_desc: string
    step_2_title: string
    step_2_desc: string
    step_3_title: string
    step_3_desc: string
    accepted_documents: string
    doc_passport: string
    doc_id_card: string
    doc_driving_license: string
    initiating: string
    redirect_notice: string
    follow_instructions: string
    secure_verification: string
    uploaded_documents: string
    document_front: string
    document_back: string
    selfie: string
    steps: string
    personal_info: string
    personal_info_desc: string
    document_info: string
    document_info_desc: string
    review_submit: string
    review_submit_desc: string
    secure: string
    secure_desc: string
    first_name: string
    first_name_placeholder: string
    last_name: string
    last_name_placeholder: string
    date_of_birth: string
    nationality: string
    nationality_placeholder: string
    address: string
    address_placeholder: string
    document_type: string
    passport: string
    national_id: string
    drivers_license: string
    document_number: string
    document_number_placeholder: string
    issuing_country: string
    issuing_country_placeholder: string
    document_upload_next: string
    document_upload_next_desc: string
    processing_time: string
    processing_time_desc: string
    submission_success: string
    submit_verification: string
    errors: {
      first_name_required: string
      last_name_required: string
      date_of_birth_required: string
      nationality_required: string
      address_required: string
      document_type_required: string
      document_number_required: string
      issuing_country_required: string
      document_front_required: string
      document_back_required: string
      selfie_required: string
    }
  }
  payment: {
    payment_required: string
    payment_instructions: string
    payment_description: string
    send_exact_amount: string
    kyc_verification: string
    efm_membership: string
    kyc_description: string
    efm_description: string
    validity_one_year: string
    unit: string
    quantity: string
    total: string
    choose_method: string
    choose_product: string
    choose_product_description: string
    payment_method: string
    cryptocurrencies: string
    other_methods: string
    card: string
    bank_transfer: string
    network: string
    amount_to_send: string
    receiving_address: string
    bank_details: string
    beneficiary: string
    bank_reference_info: string
    network_warning: string
    payment_done: string
    validation_time_info: string
    min: string
    min_amount: string
    min_amount_error: string
    enter_amount: string
    custom_amount: string
    card_coming_soon: string
    creating_payment: string
    order_id: string
    add_recipients: string
    recipients_description: string
    method_description: string
    instructions_description: string
    recipient: string
    username_or_email: string
    user_not_found: string
    product_type: string
    amount: string
    min_100: string
    add_recipient: string
    recipients_count: string
    confirm_close_title: string
    confirm_close_description: string
    pay_for_myself: string
    pay_for_others: string
    add_other_user: string
    checking: string
    waiting_confirmation: string
    not_received: string
    success_title: string
    success_description: string
    amount_paid: string
    auto_checking: string
    last_check: string
    waiting_payment: string
    confirming: string
    partially_paid: string
  }
  contests: {
    profile_incomplete_title: string
    profile_incomplete_message: string
    complete_profile: string
    kyc_required_title: string
    kyc_required_message: string
    kyc_recommended_title: string
    kyc_recommended_message: string
    verify_identity: string
  }
  user: {
    profile: string
    settings: string
    kyc: string
    subscription: string
    logout: string
    view_more: string
  }
  notifications: {
    title: string
    no_notifications: string
    mark_all_read: string
    mark_as_read: string
    types: {
      system: string
      contest: string
      compte: string
    }
    messages: {
      new_vote: string
      new_comment: string
      new_reply: string
      new_like: string
      new_reaction: string
    }
    time: {
      just_now: string
      seconds_ago: string
      minute_ago: string
      minutes_ago: string
      hour_ago: string
      hours_ago: string
      day_ago: string
      days_ago: string
      week_ago: string
      weeks_ago: string
      month_ago: string
      months_ago: string
      year_ago: string
      years_ago: string
    }
  }
  pages: {
    contests: {
      badge: string
      title: string
      subtitle: string
      search_placeholder: string
      filters: {
        all: string
        city: string
        country: string
        regional: string
        continental: string
        global: string
      }
      stats: {
        active: string
        participants: string
        levels: string
      }
      all_contests: string
      contests_filter: string
      results: string
      reset_filters: string
      join_community: string
      learn_more: string
      no_results: string
      try_different_filter: string
      auth_required_title: string
      auth_required_description: string
      auth_required_benefits_title: string
      auth_required_benefit_participate: string
      auth_required_benefit_view_contestants: string
      auth_required_benefit_vote: string
      auth_required_benefit_comment: string
      auth_required_login: string
      auth_required_register: string
      cta: {
        title: string
        subtitle: string
        button: string
      }
    }
    clubs: {
      title: string
      subtitle: string
      search_placeholder: string
      features: {
        dsp: string
        multi_admin: string
        affiliate: string
      }
      no_results: string
      try_different_filter: string
      cta: {
        title: string
        subtitle: string
        feature1: string
        feature2: string
        feature3: string
        button: string
      }
    }
    about: {
      title: string
      subtitle: string
      mission: {
        title: string
        description: string
      }
      values: {
        title: string
        subtitle: string
      }
      timeline: {
        title: string
      }
      team: {
        title: string
        subtitle: string
      }
      cta: {
        title: string
        subtitle: string
        button: string
      }
    }
    contact: {
      title: string
      subtitle: string
      form: {
        title: string
        name: string
        email: string
        category: string
        subject: string
        message: string
        submit: string
      }
      faq: {
        title: string
      }
      hours: {
        title: string
      }
      categories: {
        title: string
        description: string
        add_category: string
        search_placeholder: string
        no_categories: string
        no_categories_found: string
        created_at: string
        edit_category: string
        create_category: string
        edit_category_description: string
        create_category_description: string
        category_name: string
        category_name_required: string
        category_name_max_length: string
        slug: string
        slug_required: string
        slug_max_length: string
        slug_invalid: string
        slug_auto_generated: string
        description_label: string
        description_placeholder: string
        is_active: string
        cancel: string
        save: string
        saving: string
        edit: string
        create: string
        delete: string
        delete_confirm: string
        category_created: string
        category_updated: string
        category_deleted: string
        category_create_error: string
        category_update_error: string
        category_delete_error: string
        categories_load_error: string
      }
    }
  }
}

export const translations: Record<Language, TranslationKeys> = {
  fr: {
    not_found: {
      title: "Page introuvable",
      description: "Désolé, la page que vous recherchez n'existe pas ou a été déplacée.",
      go_back: "Retour",
      go_home: "Accueil",
      quick_links: "Liens rapides",
      help_text: "Si vous pensez qu'il s'agit d'une erreur, veuillez contacter notre support."
    },
    common: {
      loading: "Chargement...",
      error: "Une erreur est survenue",
      success: "Opération réussie",
      cancel: "Annuler",
      confirm: "Confirmer",
      continue: "Continuer",
      or: "ou",
      redirecting: "Redirection...",
      please_wait: "Veuillez patienter...",
      back: "Retour",
      back_to_dashboard: "Retour au tableau de bord",
      previous: "Précédent",
      next: "Suivant",
      submitting: "Envoi...",
      no_documents: "Aucun document",
      profile_setup: "Configuration du profil",
      profile_setup_description: "Complétez votre profil pour continuer",
      edit: "Modifier",
      delete: "Supprimer",
      deleting: "Suppression...",
      confirm_delete: "Confirmer la suppression",
      deleted_successfully: "Supprimé avec succès",
      likes: "J'aime",
      comments: "Commentaires",
      search: "Rechercher",
      clear: "Effacer",
      welcome: "Bienvenue",
      access_denied: "Accès refusé",
      no_permission: "Vous n'avez pas la permission d'effectuer cette action",
      refresh: "Actualiser",
      network_error: "Erreur réseau",
      optional: "(optionnel)",
      save: "Enregistrer",
      unknown: "Inconnu",
      load_more: "Charger plus",
      actions: "Actions"
    },
    admin: {
      title: "Panneau d'administration",
      subtitle: "Gérez votre plateforme",
      nav: {
        main: "Principal",
        dashboard: "Tableau de bord",
        management: "Gestion",
        seasons: "Saisons",
        contests: "Concours",
        contestants: "Candidats",
        users: "Utilisateurs",
        kyc: "KYC",
        reports: "Rapports",
        configuration: "Configuration",
        categories: "Catégories",
        commission_settings: "Paramètres de commission",
        suggested_contests: "Concours suggérés",
        transactions: "Transactions",
        microservices: "Microservices",
        accounting: "Comptabilité"
      },
      dashboard: {
        total_seasons: "Total des saisons",
        active: "actifs",
        inactive: "inactifs",
        admins: "admins",
        votes: "Votes",
        total_votes: "Total des votes",
        comments: "Commentaires",
        total_comments: "Total des commentaires",
        quick_actions: "Actions rapides",
        user_progress: "Progression des utilisateurs",
        reports: {
          title: "Rapports",
          description: "Générez et consultez vos rapports",
          financial_report: "Rapport financier",
          financial_description: "Revenus, dépenses et profits",
          users_report: "Rapport utilisateurs",
          users_description: "Statistiques et progression",
          contests_report: "Rapport concours",
          contests_description: "Performance des concours",
          votes_report: "Rapport votes",
          votes_description: "Analyse des votes",
          recent_reports: "Rapports récents"
        },
        chart_labels: {
          total_users: "Total utilisateurs",
          active_users: "Utilisateurs actifs",
          new_users: "Nouveaux utilisateurs"
        },
        periods: {
          today: "Aujourd'hui",
          yesterday: "Hier",
          week: "Semaine",
          month: "Mois",
          year: "Année"
        },
        statistics: {
          total_deposits: "Total Dépôts",
          total_withdrawals: "Total Retraits",
          verified_users: "Utilisateurs Vérifiés",
          reports: "Rapports",
          categories: "Catégories",
          deposits_chart: "Graphique des Dépôts",
          withdrawals_chart: "Graphique des Retraits",
          categories_chart: "Statistiques des Catégories",
          reports_by_type: "Rapports par Type",
          amount_eur: "Montant ($)",
          deposits_count: "dépôts",
          withdrawals_count: "retraits",
          kyc_verified: "KYC validé",
          reports_count: "Signalements",
          categories_total: "Total",
          amount: "Montant",
          count: "Nombre",
          contests: "Concours",
          uses: "Utilisations",
          period: "Période:",
          custom: "Personnalisé",
          apply: "Appliquer",
          loading: "Chargement...",
          refresh: "Actualiser",
          no_data_available: "Aucune donnée disponible"
        }
      },
      profile: {
        participations: "Participations",
        total_votes: "Votes",
        total_favorites: "Favoris",
        followers: "Abonnés",
        following: "Abonnements",
        contestants: "Participations",
        all_rounds: "Tous",
        no_entries: "Aucune participation pour le moment",
        verified: "Vérifié",
        years: "ans",
        follow: "Suivre",
        unfollow: "Ne plus suivre",
        followed: "Vous suivez cet utilisateur",
        unfollowed: "Vous ne suivez plus cet utilisateur"
      },
      rounds: {
        title: "Gestion des Rounds",
        description: "Gérez les rounds de concours",
        new_round: "Nouveau Round",
        edit: "Modifier le Round",
        create: "Créer un Round",
        contest: "Concours",
        select_contest: "Sélectionner un concours",
        name: "Nom du Round",
        status: "Statut",
        load_error: "Erreur lors du chargement des rounds",
        delete_success: "Round supprimé avec succès",
        delete_error: "Erreur lors de la suppression",
        update_success: "Round mis à jour avec succès",
        create_success: "Round créé avec succès",
        search: "Rechercher un round...",
        confirm_delete: "Supprimer le round",
        confirm_delete: "Supprimer le round",
        delete_warning: "Êtes-vous sûr de vouloir supprimer ce round ?",
        city_season: "Saison Ville",
        country_season: "Saison Pays",
        regional_season: "Saison Régionale",
        continental_season: "Saison Continentale",
        global_season: "Saison Mondiale",
        start_date: "Date de début",
        end_date: "Date de fin"
      },
      seasons: {
        title: "Gestion des Saisons",
        description: "Créez, modifiez et gérez les saisons de concours",
        new_season: "Nouvelle saison",
        edit_season: "Modifier la saison",
        create_season: "Créer une saison",
        year: "Année",
        season_number: "Numéro de saison",
        season_title: "Titre",
        status: "Statut",
        start_date: "Date de début",
        end_date: "Date de fin",
        upload_end_date: "Fin d'upload",
        upcoming: "À venir",
        upload_phase: "Phase d'upload",
        voting_active: "Vote actif",
        voting_ended: "Vote terminé",
        completed: "Terminée",
        cancelled: "Annulée",
        edit: "Modifier",
        delete: "Supprimer",
        cancel: "Annuler",
        create: "Créer",
        confirm_delete: "Êtes-vous sûr de vouloir supprimer cette saison ?",
        confirm_delete_title: "Supprimer la saison",
        confirm_delete_message: "Êtes-vous sûr de vouloir supprimer cette saison ? Cette action est irréversible.",
        no_seasons: "Aucune saison trouvée. Créez votre première saison.",
        create_success: "Saison créée avec succès",
        update_success: "Saison modifiée avec succès",
        delete_success: "Saison supprimée avec succès",
        load_error: "Erreur lors du chargement des saisons",
        save_error: "Erreur lors de la sauvegarde",
        delete_error: "Erreur lors de la suppression",
        level: "Niveau",
        level_city: "Ville",
        level_country: "Pays",
          filter_level: "Niveau",
        level_regional: "Régional",
        level_continent: "Continent",
        level_global: "Global",
        level_placeholder: "Sélectionner un niveau",
        season_title_placeholder: "Ex: Saison Printemps 2024",
        error_level_exists: "Une saison avec le niveau '{level}' existe déjà. Il ne peut y avoir qu'une seule saison active par niveau.",
        error_invalid_level: "Niveau invalide. Les niveaux valides sont: {levels}",
        contestants_count: "candidats",
        contests_count: "concours"
      },
      contests: {
        title: "Gestion des Concours",
        tab_contests: "Concours",
        tab_rounds: "Rounds",
        description: "Créez, modifiez et gérez les concours",
        new_contest: "Nouveau concours",
        edit_contest: "Modifier le concours",
        create_contest: "Créer un concours",
        name: "Nom du concours",
        contest_description: "Description du concours",
        contest_type: "Type de concours",
        level: "Niveau",
        city: "Ville",
        country: "Pays",
        region: "Région",
        continent: "Continent",
        global: "Mondial",
        active: "Actif",
        inactive: "Inactif",
        upload_open: "Upload ouvert",
        voting_active: "Vote actif",
        edit: "Modifier",
        delete: "Supprimer",
        cancel: "Annuler",
        confirm_delete: "Êtes-vous sûr de vouloir supprimer ce concours ?",
        image: "Image du concours",
        no_contests: "Aucun concours trouvé",
        voting_restriction: "Restriction de vote",
        none: "Aucune",
        male_only: "Hommes uniquement",
        female_only: "Femmes uniquement",
        geographic: "Géographique",
        age_restricted: "Restriction d'âge",
        start_date: "Date de début",
        end_date: "Date de fin",
        search_placeholder: "Rechercher des concours...",
        sort: "Trier par",
        season: "Saison",
        select_season: "Sélectionner une saison",
        delete_warning: "Cette action est irréversible. Voulez-vous vraiment supprimer ce concours ?",
        create_success: "Concours créé avec succès",
        create_error: "Erreur lors de la création du concours",
        update_success: "Concours mis à jour avec succès",
        update_error: "Erreur lors de la mise à jour du concours",
        delete_success: "Concours supprimé avec succès",
        delete_error: "Erreur lors de la suppression du concours",
        sort_date: "Date (Récent)",
        sort_name: "Nom (A-Z)",
        sort_status: "Statut",
        participant_count: "Nombre de participants",
        all_loaded: "Tous les concours affichés",
        creating: "Création...",
        updating: "Mise à jour...",
        candidates: "Candidats",
        confirm_delete_title: "Supprimer le concours",
        confirm_delete_message: "Êtes-vous sûr de vouloir supprimer ce concours ? Cette action est irréversible.",
        submission_start: "Début des uploads",
        submission_end: "Fin des uploads",
        voting_start: "Début du vote",
        voting_end: "Fin du vote",
        contest_dates: "Dates du concours",
        approved: "Approuvé",
        rejected: "Rejeté",
        filter: "Filtrer",
        approve: "Approuver",
        reject: "Rejeter",
        view: "Voir",
        no_kyc: "Aucune vérification KYC",
        verification_score: "Score de confiance",
        identity: "Identité",
        document: "Document",
        address: "Adresse",
        face: "Visage",
        confidence_score: "Score",
        rejection_reason: "Raison du rejet",
        // Verification form labels
        participant_type: "Type de participant",
        verification_type: "Type de vérification",
        min_age: "Âge minimum",
        max_age: "Âge maximum",
        requires_kyc: "KYC obligatoire",
        requires_visual: "Vérif. visuelle",
        requires_voice: "Vérif. vocale",
        requires_brand: "Vérif. marque",
        requires_content: "Vérif. propriété du contenu",
        // List stats
        participants: "Participants",
        pending: "En attente",
        // Media requirements
        media_requirements: "Exigences Média",
        requires_video: "Vidéo obligatoire",
        max_videos: "Vidéos max",
        video_duration: "Durée max (min)",
        min_images: "Images min",
        max_images: "Images max",
        // List translations
        level_city: "Ville",
        level_country: "Pays",
          filter_level: "Niveau",
        level_region: "Région",
        level_continent: "Continent",
        level_global: "Mondial",
        contests_count: "concours",
        active_count: "actifs",
        result: "résultat",
        results: "résultats",
        found: "trouvé(s)",
        no_results_for: "Aucun résultat pour",
        current_image: "Image actuelle",
        participant_individual: "Individuel",
        participant_pet: "Animal",
        participant_club: "Club",
        participant_content: "Contenu",
        kyc_required: "KYC requis",
        kyc_not_required: "Sans KYC",
        verification_visual: "Visuel",
        verification_voice: "Vocal",
        verification_brand: "Marque",
        verification_content: "Contenu",
        age_restricted: "Restriction d'âge",
        years: "ans",
        // Form placeholders
        name_placeholder: "Ex: Concours de beauté 2024",
        description_placeholder: "Description du concours",
        type_placeholder: "Ex: beauty, handsome",
        // Auto dates
        auto_dates_title: "Dates automatiques",
        auto_dates_description: "Les dates sont générées automatiquement",
        auto_date_upload_start: "Début des uploads : date de création",
        auto_date_upload_end: "Fin des uploads : 1 mois après le début",
        auto_date_vote_start: "Début du vote : 1 jour après la fin des uploads",
        auto_date_vote_end: "Fin du vote : 1 mois après le début du vote",
        // Additional form labels
        verification_requirements: "Exigences de vérification",
        verification_none: "Aucune",
        none: "Aucune",
        male_only: "Hommes uniquement",
        female_only: "Femmes uniquement",
        geographic: "Géographique",
        // Additional placeholders
        min_age_placeholder: "Ex: 18",
        max_age_placeholder: "Ex: 35",
        search_input_placeholder: "Nom, type, description...",
        sort: "Trier par",
        season: "Saison",
        select_season: "Sélectionner une saison",
        delete_warning: "Cette action est irréversible. Voulez-vous vraiment supprimer ce concours ?",
        // Season dates
        season_dates: "Dates des saisons",
        season_dates_description_edit: "Ces dates sont calculées automatiquement à partir de la date de début de vote. Vous pouvez les modifier manuellement si nécessaire.",
        season_dates_description_create: "Ces dates seront calculées automatiquement à partir de la date de début de vote lors de la création. Vous pouvez les pré-remplir si nécessaire.",
        city_season: "Saison Ville",
        country_season: "Saison Pays",
        regional_season: "Saison Régionale",
        continental_season: "Saison Continentale",
        global_season: "Saison Globale",
        start_date: "Date de début",
        end_date: "Date de fin",
        // Voting type translations
        voting_type: "Type de compétition",
        select_voting_type: "Sélectionner un type de compétition",
        new_voting_type: "Nouveau type de vote",
        voting_types_load_error: "Erreur lors du chargement des types de vote",
        voting_type_created: "Type de vote créé avec succès",
        voting_type_create_error: "Erreur lors de la création du type de vote",
        create_voting_type: "Créer un type de vote",
        voting_type_name_placeholder: "Ex: Vote City - Commission Advert",
        voting_level: "Niveau de vote",
        commission_source: "Source de commission",
        commission_rules: "Règles de commission (JSON)",
        commission_rules_help: "Les règles de commission sont optionnelles. Format: L1 pour le niveau 1, L2-10 pour les niveaux 2 à 10.",
        commission_advert: "Publicité",
        commission_affiliate: "Affiliation",
        commission_kyc: "KYC",
        commission_mfm: "MFM",
        create: "Créer",
        // Dialog titles
        create_nomination_contest: "Créer un nouveau (Concours Nomination)",
        create_participation_contest: "Créer un nouveau (Concours Participation)",
        // Error messages
        error_name_required: "Le nom du concours est obligatoire",
        error_category_required: "La catégorie est obligatoire",
        error_description_required: "La description est obligatoire",
        error_image_required: "L'image du concours est obligatoire",
        error_contest_type_required: "Le type de compétition est obligatoire pour les nominations",
        // Category translations
        category: "Catégorie",
        select_category: "Sélectionner une catégorie",
        no_category: "Aucune catégorie",
        add_category: "Ajouter une catégorie",
        create_category: "Créer une catégorie",
        category_name_required: "Le nom de la catégorie est requis",
        category_created: "Catégorie créée avec succès",
        category_create_error: "Erreur lors de la création de la catégorie",
        categories_load_error: "Erreur lors du chargement des catégories",
        category_name_placeholder: "Ex: Pop, Rock, Hip hop",
        slug: "Slug",
        slug_placeholder: "Ex: pop, rock, hip-hop",
        slug_help: "Le slug est généré automatiquement à partir du nom. Vous pouvez le modifier si nécessaire.",
        category_description_placeholder: "Description de la catégorie (optionnel)",
        contest_type_auto_filled: "Le type de concours est automatiquement rempli à partir de la catégorie",
        verification_requirements: "Exigences de vérification",
        media_requirements: "Exigences Média",
        participant_individual: "Individuel",
        participant_pet: "Animal",
        participant_club: "Club",
        verification_video_max_duration: "Durée max vidéo vérif (sec)",
        verification_max_size_mb: "Taille max vérif (MB)",
        new_participation: "Nouveau (Participation)",
        new_nomination: "Nouveau (Nomination)",
        min_images: "Min Images",
        max_images: "Max Images",
        min_age: "Age Minimum",
        max_age: "Age Maximum",
        max_videos: "Max Vidéos",
        video_max_duration: "Durée max vidéo (sec)",
        video_max_size_mb: "Taille max vidéo (MB)",
        requires_video: "Vidéo Requise",
        kyc_required: "KYC Requis",
        verification_visual: "Vérification Visuelle",
        verification_voice: "Vérification Vocale",
        verification_brand: "Vérification de Marque",
        verification_content: "Vérification de Contenu"
      },
      contestants: {
        title: "Gestion des Candidats",
        description: "Approuvez ou rejetez les candidatures",
        search_placeholder: "Rechercher par nom ou titre...",
        all: "Tous",
        pending: "En attente",
        verified: "Vérifiés",
        filter: "Filtrer",
        approve: "Approuver",
        reject: "Rejeter",
        view: "Voir",
        author: "Auteur",
        images: "Images",
        videos: "Vidéos",
        votes: "Votes",
        comments: "Commentaires",
        status: "Statut",
        registration_date: "Date d'inscription",
        actions: "Actions",
        contestant_details: "Détails du candidat",
        close: "Fermer",
        no_contestants: "Aucun candidat trouvé",
        status_pending: "En attente",
        status_verified: "Vérifié",
        status_rejected: "Rejeté",
        approve_success: "Candidat approuvé avec succès",
        approve_error: "Erreur lors de l'approbation du candidat",
        reject_success: "Candidat rejeté avec succès",
        reject_error: "Erreur lors du rejet du candidat",
        status_update_success: "Statut du candidat mis à jour avec succès",
        status_update_error: "Erreur lors de la mise à jour du statut",
        comment_delete_success: "Commentaire supprimé avec succès",
        comment_delete_error: "Erreur lors de la suppression du commentaire",
        comment_hide_success: "Commentaire caché avec succès",
        comment_hide_error: "Erreur lors du masquage du commentaire",
        comment_show_success: "Commentaire affiché avec succès",
        comment_show_error: "Erreur lors de l'affichage du commentaire",
        comment_restore_success: "Commentaire restauré avec succès",
        comment_restore_error: "Erreur lors de la restauration du commentaire",
        new_contestant: "Nouveau candidat",
        edit_contestant: "Modifier le candidat",
        user: "Utilisateur",
        select_user: "Sélectionner un utilisateur",
        select_season: "Sélectionner une saison",
        no_seasons_for_level: "Aucune saison disponible pour ce niveau",
        title_placeholder: "Titre du candidat",
        description_placeholder: "Description du candidat",
        create_success: "Candidat créé avec succès",
        update_success: "Candidat mis à jour avec succès",
        save_error: "Erreur lors de la sauvegarde",
        seasons_load_error: "Erreur lors du chargement des saisons",
        no_seasons_available: "Aucune saison disponible. Veuillez créer une saison d'abord."
      },
      categories: {
        title: "Gestion des Catégories",
        description: "Créez et gérez les catégories de concours",
        add_category: "Ajouter une catégorie",
        search_placeholder: "Rechercher une catégorie...",
        no_categories: "Aucune catégorie pour le moment",
        no_categories_found: "Aucune catégorie trouvée",
        created_at: "Créé le",
        edit_category: "Modifier la catégorie",
        create_category: "Créer une nouvelle catégorie",
        edit_category_description: "Modifiez les informations de la catégorie",
        create_category_description: "Remplissez les informations pour créer une nouvelle catégorie",
        category_name: "Nom",
        category_name_required: "Le nom est requis",
        category_name_max_length: "Le nom ne peut pas dépasser 100 caractères",
        slug: "Slug",
        slug_required: "Le slug est requis",
        slug_max_length: "Le slug ne peut pas dépasser 100 caractères",
        slug_invalid: "Le slug ne peut contenir que des lettres minuscules, des chiffres et des tirets",
        slug_auto_generated: "Le slug est généré automatiquement à partir du nom",
        description_label: "Description",
        description_placeholder: "Description de la catégorie (optionnel)",
        is_active: "Catégorie active",
        cancel: "Annuler",
        save: "Enregistrer",
        saving: "Enregistrement...",
        edit: "Modifier",
        create: "Créer",
        delete: "Supprimer",
        delete_confirm: "Êtes-vous sûr de vouloir supprimer la catégorie",
        category_created: "Catégorie créée avec succès",
        category_updated: "Catégorie mise à jour avec succès",
        category_deleted: "Catégorie supprimée avec succès",
        category_create_error: "Erreur lors de la création de la catégorie",
        category_update_error: "Erreur lors de la mise à jour de la catégorie",
        category_delete_error: "Erreur lors de la suppression de la catégorie",
        categories_load_error: "Erreur lors du chargement des catégories"
      },
      kyc: {
        title: "Gestion KYC",
        description: "Approuvez ou rejetez les vérifications d'identité",
        search_placeholder: "Rechercher par email ou nom...",
        pending: "En attente",
        approved: "Approuvés",
        rejected: "Rejetés",
        filter: "Filtrer",
        approve: "Approuver",
        reject: "Rejeter",
        view: "Détails",
        no_kyc: "Aucune vérification KYC trouvée",
        verification_score: "Score de confiance",
        identity: "Identité",
        document: "Document",
        address: "Adresse",
        face: "Visage",
        confidence_score: "Score",
        rejection_reason: "Raison du rejet"
      },
      reports: {
        title: "Gestion des Rapports",
        description: "Gérez les signalements de contenus",
        search_placeholder: "Rechercher un rapport...",
        all: "Tous",
        pending: "En attente",
        reviewed: "Révisés",
        resolved: "Résolus",
        no_reports: "Aucun rapport pour le moment",
        no_reports_found: "Aucun rapport trouvé",
        report_number: "Rapport #",
        reason: "Raison",
        description_label: "Description",
        status: "Statut",
        details: "Détails",
        reported_contestant: "Contestant signalé",
        contestant_author: "Auteur du contestant",
        reporter: "Signaleur",
        contest: "Concours",
        created_at: "Créé le",
        reviewed_at: "Révisé le",
        moderator_notes: "Notes du modérateur",
        verification_status: "Statut de vérification",
        verification_status_pending: "En attente",
        verification_status_approved: "Approuvé",
        verification_status_rejected: "Rejeté",
        reason_spam: "Spam",
        reason_inappropriate: "Contenu inapproprié",
        reason_harassment: "Harcèlement",
        reason_fake: "Compte faux",
        reason_copyright: "Violation de droits d'auteur",
        reason_other: "Autre",
        no_title: "Sans titre",
        load_error: "Erreur lors du chargement des rapports",
        report_details: "Détails du rapport",
        report_details_description: "Informations complètes sur le signalement",
        reason_label: "Raison du signalement"
      },
      suggested_contests: {
        title: "Suggestions de Concours",
        description: "Gérez les suggestions de concours proposées par les utilisateurs",
        search_placeholder: "Rechercher une suggestion...",
        all: "Tous",
        pending: "En attente",
        approved: "Approuvés",
        rejected: "Rejetés",
        no_suggestions: "Aucune suggestion pour le moment",
        no_suggestions_found: "Aucune suggestion trouvée",
        author: "Auteur",
        author_not_available: "Auteur non disponible",
        unknown_date: "Date inconnue",
        details: "Détails",
        contest_suggestion_details: "Détails de la suggestion de concours",
        status: "Statut",
        category: "Catégorie",
        description: "Description",
        verified: "Vérifié",
        dates: "Dates",
        created_at: "Créé le",
        updated_at: "Modifié le",
        load_error: "Erreur lors du chargement des suggestions"
      },
      transactions: {
        title: "Gestion des Transactions",
        description: "Consultez toutes les transactions (dépôts, retraits, etc.)",
        search_placeholder: "Rechercher par référence, description, utilisateur...",
        all_types: "Tous les types",
        all_statuses: "Tous les statuts",
        no_transactions: "Aucune transaction pour le moment",
        no_transactions_found: "Aucune transaction trouvée",
        transaction: "Transaction",
        transaction_details: "Détails de la transaction",
        transaction_details_description: "Informations complètes sur la transaction",
        type: {
          deposit: "Dépôt",
          withdrawal: "Retrait",
          entry_fee: "Frais d'entrée",
          prize_payout: "Gain",
          commission: "Commission",
          refund: "Remboursement"
        },
        status: {
          pending: "En attente",
          completed: "Complété",
          failed: "Échoué",
          cancelled: "Annulé"
        },
        user: "Utilisateur",
        contest: "Concours",
        payment_method: "Méthode de paiement",
        product_type: "Type de produit",
        amount: "Montant",
        currency: "Devise",
        description: "Description",
        reference: "Référence",
        order_id: "ID Commande",
        external_payment_id: "ID Paiement Externe",
        tx_hash: "Hash Transaction",
        created_at: "Créé le",
        processed_at: "Traité le",
        validated_at: "Validé le",
        type_label: "Type",
        status_label: "Statut",
        details: "Détails",
        search: "Rechercher",
        load_error: "Erreur lors du chargement des transactions"
      },
      accounting: {
        title: "Comptabilité",
        subtitle: "Vue d'ensemble financière et journal des écritures",
        refresh: "Actualiser",
        total_revenue: "Revenus Totaux",
        ytd: "Depuis le début de l'exercice",
        journal_tab: "Journal Général",
        coa_tab: "Plan Comptable",
        journal_title: "Journal des Écritures",
        journal_desc: "Les 50 dernières écritures comptables",
        coa_title: "Plan Comptable",
        coa_desc: "Liste des comptes et soldes actuels",
        table: {
          date: "Date",
          ref: "N° Pièce",
          description: "Description",
          debit: "Débit",
          credit: "Crédit",
          status: "Statut",
          code: "Code",
          account: "Nom du Compte",
          type: "Type",
          balance: "Solde"
        },
        error_loading: "Erreur lors du chargement des données comptables",
        retry: "Réessayer",
        no_journal: "Aucune écriture au journal pour le moment.",
        no_coa: "Aucun compte dans la base. Exécutez init_chart_of_accounts sur le serveur.",
        reports_tab: "Rapports financiers",
        reports_hint:
          "Grand livre, balance de vérification, bilan, compte de résultat et synthèse trésorerie USDT (BSC) (aperçu).",
        load_report: "Charger le rapport",
        as_of_date: "À la date du",
        period_from: "Du",
        period_to: "Au",
        balance_sheet_title: "Bilan",
        income_statement_title: "Compte de résultat",
        trial_balance_title: "Balance de vérification",
        cash_flow_title: "Trésorerie USDT (BSC) (résumé)",
        general_ledger_title: "Grand livre (compte)",
        select_account: "Compte",
        section_assets: "Actifs",
        section_liabilities: "Passifs",
        section_equity: "Capitaux propres",
        total_assets: "Total actifs",
        total_liabilities: "Total passifs",
        total_equity: "Total capitaux propres",
        balanced_ok: "Équilibre : actifs = passifs + capitaux",
        balanced_no: "Écart (arrondi ou comptes hors bilan)",
        revenues: "Produits",
        expenses: "Charges",
        net_income: "Résultat net",
        statement_total_revenue: "Total produits",
        statement_total_expenses: "Total charges",
        total_debits: "Total débits",
        total_credits: "Total crédits",
        trial_balanced: "Balance équilibrée",
        trial_not_balanced: "Écart débits / crédits",
        operating: "Activités opérationnelles",
        note: "Note",
        opening_balance: "Solde d'ouverture",
        closing_balance: "Solde de clôture",
        gl_lines: "Lignes",
        no_report_data: "Aucune donnée pour cette période.",
        report_failed: "Échec du rapport",
        full_pack_tab: "Dossier complet",
        full_pack_hint:
          "Bilan, compte de résultat, balance, synthèse trésorerie USDT (BSC), registre du plan comptable et mouvements de période — basé sur les écritures validées.",
        download_json: "Télécharger JSON",
        download_coa_csv: "CSV plan comptable",
        summary_checks: "Contrôles",
        coa_register_title: "Registre du plan comptable (tous les comptes)",
        period_activity_title: "Mouvements de la période par compte",
        equity_highlights: "Capitaux propres (aperçu)",
        parent_code: "Compte parent",
        treasury_change_1001: "Variation trésorerie USDT (BSC) (1001)",
        cf_1001_opening: "Solde d'ouverture — USDT (BSC) compte 1001",
        cf_1001_closing: "Solde de clôture — USDT (BSC) compte 1001"
      },
      commission_settings: {
        subtitle: "Configurez les règles et taux de commission",
        coming_soon: "Cette section est en cours de développement. Les paramètres des commissions seront disponibles prochainement."
      },
      microservices: {
        subtitle: "Gérez et surveillez les microservices",
        coming_soon: "Cette section est en cours de développement. La gestion des microservices sera disponible prochainement."
      },
      users: {
        title: "Gestion des Utilisateurs",
        description: "Gérez les rôles et les permissions des utilisateurs",
        search_placeholder: "Rechercher par email, nom ou pseudo...",
        all: "Tous",
        admins: "Admins",
        verified: "Vérifiés",
        inactive: "Inactifs",
        filter: "Filtrer",
        table_user: "Utilisateur",
        table_email: "Email",
        table_participations: "Participations",
        table_prizes: "Prix",
        table_candidates: "Candidats",
        table_contests: "Contests",
        table_status: "Statut",
        table_actions: "Actions",
        make_admin: "Faire Admin",
        remove_admin: "Retirer Admin",
        activate: "Activer",
        deactivate: "Désactiver",
        no_users: "Aucun utilisateur trouvé",
        registered: "Inscrit le",
        inactive_status: "Inactif",
        user: "Utilisateur",
        email: "Email",
        participations: "Participations",
        prizes: "Prix",
        candidates: "Candidats",
        contests: "Contests",
        status: "Statut",
        actions: "Actions",
        details: "Détails",
        comments: "Commentaires",
        view_comments: "Voir les commentaires",
        no_comments: "Aucun commentaire",
        comment_text: "Texte",
        comment_date: "Date",
        comment_author: "Auteur",
        city: "Ville",
        country: "Pays",
        continent: "Continent",
        region: "Région",
        kyc_status: "Statut KYC",
        kyc_verified: "Vérifié",
        kyc_pending: "En attente",
        date_of_birth: "Date de naissance",
        phone: "Téléphone",
        bio: "Biographie",
        last_login: "Dernière connexion",
        joined: "Inscrit",
        participations_count: "Participations",
        prizes_count: "Prix",
        contestants_count: "Candidats",
        contests_participated: "Contests",
        confirm_delete_title: "Supprimer l'utilisateur",
        confirm_delete_message: "Êtes-vous sûr de vouloir supprimer cet utilisateur ? Cette action est irréversible.",
        delete: "Supprimer",
        cancel: "Annuler",
        delete_success: "Utilisateur supprimé avec succès",
        delete_error: "Erreur lors de la suppression",
        personal_info: "Informations personnelles",
        account_status: "Statut du compte",
        verify_kyc: "Vérifier KYC",
        unverify_kyc: "Révoquer KYC",
        kyc_verify_success: "KYC vérifié avec succès",
        kyc_unverify_success: "Vérification KYC révoquée",
        toggle_admin_success: "Droits admin modifiés",
        toggle_admin_error: "Erreur lors de la modification du rôle",
        toggle_active_success_deactivate: "Utilisateur désactivé",
        toggle_active_success_activate: "Utilisateur activé",
        toggle_active_error: "Erreur lors de la modification du statut",
        load_error: "Erreur lors du chargement des utilisateurs",
        load_details_error: "Erreur lors du chargement des détails",
        edit_comment: "Éditer",
        delete_comment: "Supprimer",
        hide_comment: "Masquer",
        show_comment: "Afficher",
        comment_edit_success: "Commentaire modifié",
        comment_delete_success: "Commentaire supprimé",
        comment_hide_success: "Commentaire masqué",
        comment_show_success: "Commentaire affiché",
        comment_edit_error: "Erreur lors de la modification",
        comment_delete_error: "Erreur lors de la suppression",
        comment_hide_error: "Erreur lors du masquage",
        comment_show_error: "Erreur lors de l'affichage",
        contest_label: "Concours",
        contestant_label: "Candidat"
      },
      reports: {
        title: "Rapports",
        description: "Gérer les signalements de contenus",
        pending: "en attente",
        reviewed: "révisés",
        resolved: "résolus",
        search_placeholder: "Rechercher par raison ou type...",
        filter: "Filtrer",
        all: "Tous",
        no_reports: "Aucun rapport trouvé",
        reporter: "Signaleur",
        reported_content: "Contenu signalé",
        reason: "Raison",
        status: "Statut",
        date: "Date",
        actions: "Actions",
        view: "Voir",
        mark_reviewed: "Marquer comme révisé",
        mark_resolved: "Marquer comme résolu",
        details: "Détails",
        close: "Fermer",
        report_details: "Détails du rapport",
        reported_by: "Signalé par",
        reported_at: "Signalé le",
        report_reason: "Raison du signalement",
        report_description: "Description",
        report_status: "Statut",
        moderator_notes: "Notes du modérateur",
        reviewed_by: "Révisé par",
        reviewed_at: "Révisé le",
        content_type: "Type de contenu",
        contestant: "Candidat",
        comment: "Commentaire",
        media: "Média",
        user: "Utilisateur",
        mark_reviewed_success: "Rapport marqué comme révisé",
        mark_reviewed_error: "Erreur lors de la mise à jour",
        mark_resolved_success: "Rapport marqué comme résolu",
        mark_resolved_error: "Erreur lors de la mise à jour",
        load_error: "Erreur lors du chargement des rapports"
      },
      search: {
        placeholder: "Rechercher...",
        title: " Recherche",
        description: "Trouvez des concours, des participants, des clubs et des produits",
        no_results: "Aucun résultat trouvé",
        start_typing: "Commencez à taper pour rechercher...",
        contest: "Concours",
        contestant: "Participant",
        club: "Club",
        product: "Produit",
        recent_searches: "Recherches récentes",
        no_history: "Aucune recherche récente."
      },
      nav: {
        home: "Accueil",
        overview: "Vue d'ensemble",
        feed: "Feed",
        contests: "Concours",
        groups: "Groupes",
        my_applications: "Mes Candidatures",
        clubs: "Clubs",
        myhigh5: "MyHigh5",
        favorites: "Favoris",
        search: "Recherche",
        pages: "Pages",
        wallet: "Portefeuille",
        affiliates: "Affiliés",
        commissions: "Commissions",
        leaderboard: "Classement",
        prize: "Prix",
        shop: "Boutique",
        main: "Principal",
        competitions: "Compétitions",
        business: "Affaires",
        resources: "Ressources",
        founding_member: "Founding Membership",
        affiliate_program: "Programme d'Affiliation",
        affiliate_agreement: "Accord d'Affiliation",
        account: "Compte",
        settings: "Paramètres",
        admin: "Administration",
        admin_panel: "Panneau Admin",
        admin_panel_desc: "Gérer la plateforme",
        notifications: "Notifications",
        notifications_desc: "Voir toutes vos notifications",
        messages: "Messages",
        following: "Abonnements",
        social: "Social",
        feed: "Feed"
      },
      feed: {
        welcome: "Bienvenue sur votre feed !",
        welcome_description: "Commencez à suivre des personnes pour voir leurs posts ici.",
        create_first_post: "Créer votre premier post",
        loading: "Chargement...",
        load_more: "Charger plus",
        create_post: "Créer un post",
        delete_confirm: "Êtes-vous sûr de vouloir supprimer ce post ?",
        create_post_placeholder: "Quoi de neuf ?",
        media: "Médias",
        video: "Vidéo",
        poll: "Sondage",
        emoji: "Emoji",
        schedule: "Planifier",
        location: "Localisation",
        publish: "Publier",
        delete: "Supprimer",
        report: "Signaler",
        suggested_users: "Suggestions pour vous",
        suggested_groups: "Groupes suggérés",
        see_more: "Voir plus",
        ad_title: "Découvrez nos fonctionnalités premium",
        ad_description: "Accédez à des fonctionnalités exclusives et boostez votre visibilité",
        ad_cta: "En savoir plus",
        create_post_dialog_title: "Créer une publication",
        publishing: "Publication...",
        post_tab: "Publication",
        poll_tab: "Sondage",
        post_placeholder: "Quoi de neuf ?",
        files_selected: "fichier(s) sélectionné(s)",
        poll_question_placeholder: "Posez votre question...",
        poll_options_label: "Options du sondage",
        poll_option_placeholder: "Option",
        add_poll_option: "Ajouter une option",
        public_visibility: "Public",
        followers_visibility: "Abonnés",
        private_visibility: "Privé",
        comments: "Commentaires",
        no_comments: "Aucun commentaire",
        add_comment_placeholder: "Ajouter un commentaire...",
        comment_shortcut: "Ctrl+Entrée pour publier",
        posting: "Publication...",
        post: "Publier",
        comment_success: "Commentaire publié avec succès !",
        comment_error: "Échec de la publication du commentaire. Veuillez réessayer.",
        post_success: "Publication créée avec succès !",
        post_error: "Échec de la création de la publication. Veuillez réessayer.",
        link_copied: "Lien copié dans le presse-papiers",
        share_failed: "Impossible de partager. Essayez de copier le lien.",
        repost_failed: "Impossible d'enregistrer le repost. Réessayez.",
        repost: "Republier",
        share: "Partager"
      },
      messages: {
        title: "Messages",
        subtitle: "Messages chiffrés de bout en bout",
        no_conversations: "Aucune conversation",
        start_conversation: "Commencez une nouvelle conversation",
        encrypted_message: "Message chiffré",
        end_to_end_encrypted: "Chiffré de bout en bout",
        type_message: "Tapez un message...",
        select_conversation: "Sélectionnez une conversation",
        select_conversation_desc: "Choisissez une conversation pour commencer à discuter",
        message_button: "Message",
        new_message: "Commencer un nouveau message"
      },
      groups: {
        title: "Groupes",
        subtitle: "Rejoignez des groupes et partagez avec votre communauté",
        search_placeholder: "Rechercher un groupe...",
        no_groups_found: "Aucun groupe trouvé",
        no_groups_available: "Aucun groupe disponible",
        try_keywords: "Essayez avec d'autres mots-clés",
        be_first: "Soyez le premier à créer un groupe !",
        create_group: "Créer un groupe",
        members: "membres",
        no_members: "Aucun membre pour le moment",
        no_messages: "Aucun message pour le moment",
        join_to_chat: "Rejoignez le groupe pour discuter",
        created_by: "Créé par",
        leave: "Quitter",
        join: "Rejoindre",
        create_new_group: "Créer un nouveau groupe",
        group_name: "Nom du groupe",
        group_name_placeholder: "Nom du groupe",
        description: "Description",
        description_placeholder: "Description du groupe (optionnel)",
        group_type: "Type de groupe",
        public: "Public",
        private: "Privé",
        cancel: "Annuler",
        creating: "Création...",
        create_group_button: "Créer le groupe"
      },
      following: {
        title: "Réseau Social",
        subtitle: "Gérez vos abonnements et découvrez de nouveaux utilisateurs",
        following_tab: "Abonnements",
        followers_tab: "Abonnés",
        suggested_tab: "Suggestions",
        search_placeholder: "Rechercher...",
        no_users_found: "Aucun utilisateur trouvé",
        no_users: "Aucun utilisateur",
        followers: "abonnés",
        posts: "posts",
        unfollow: "Ne plus suivre",
        follow: "Suivre"
      },
      stats: {
        contests: "Mes Concours",
        clubs: "Mes Clubs",
        favorites: "Mes Favoris",
        points: "Mes Points"
      },
      quick_actions: "Actions Rapides",
      recent_activity: "Activité Récente",
      no_activity: "Aucune activité récente",
      position: {
        title: "Ma Position",
        no_contests: "Aucun concours en cours",
        rank: "Rang",
        points: "Points",
        contests: "Concours Beauté",
        clubs: "Club Premium",
        affiliates: "Affiliés",
        status: "Statut",
        members: "Membres",
        referrals: "Référrés",
        commissions: "Commissions",
        active: "Actif"
      },
      contests: {
        title: "Concours",
        subtitle: "Découvrez et participez aux concours de votre ville et de votre pays",
        description: "Découvrez et participez aux concours les plus populaires",
        no_contests: "Aucun concours disponible",
        no_description: "Aucune description disponible",
        all: "Tout",
        nomination: "Nominations",
        participations: "Participations",
        filter_level: "Niveau",
        level_city: "Ville",
        level_country: "Pays",
        all_levels: "Tous les niveaux",
        nomination_hint: "Nominez d'autres personnes pour les faire participer aux compétitions. Votez pour les candidats nominés par leurs fans.",
        participations_hint: "Participez vous-même aux compétitions. Les candidats s'inscrivent directement pour concourir.",
        nominate: "Nommer",
        edit_nomination: "Modifier votre Nomination",
        edit_participation: "Modifier votre Participation",
        edit: "Modifier",
        tooltip_nominate: "Cliquez pour nommer à ce concours et soumettre votre candidature",
        time_remaining_to_nominate: "Temps restant pour nommer",
        search_placeholder: "Rechercher un concours...",
        search_button: "Rechercher",
        sort: "Trier par",
        sort_participants: "Plus de participants",
        sort_votes: "Plus de votes",
        sort_date: "Plus récent",
        sort_name: "Nom (A-Z)",
        filter_continent: "Continent",
        filter_country: "Pays",
        all_countries: "Tous les pays",
        search_country_placeholder: "Rechercher un pays...",
        no_country_found: "Aucun pays trouvé",
        continents: {
          all: "Tous les continents",
          africa: "Afrique",
          asia: "Asie",
          europe: "Europe",
          north_america: "Amérique du Nord",
          south_america: "Amérique du Sud",
          oceania: "Océanie",
          antarctica: "Antarctique"
        },
        my_continent: "Mon continent",
        my_country: "Mon pays",
        voting_type: "Type de vote",
        voting_level_country: "National",
        voting_level_city: "Ville",
        voting_level_regional: "Régional",
        voting_level_continent: "Continental",
        voting_level_global: "Global",
        status: "Statut",
        level: "Niveau",
        city: "Ville",
        country: "National",
        continental: "Continental",
        regional: "Régional",
        global: "Global",
        contestants: "Participants",
        likes: "J'aime",
        comments: "Commentaires",
        received: "Reçu",
        participate: "Participer",
        be_first_to_nominate: "Soyez le premier à nommer !",
        be_first_to_participate: "Soyez le premier à participer !",
        empty_nomination_message: "Aucune nomination pour le moment. Commencez en nommant quelqu'un de votre pays !",
        empty_participation_message: "Aucun participant pour le moment. Soyez le premier à participer à ce concours !",
        tips: "Astuces",
        tip_nomination_video: "Importez du contenu vidéo",
        tip_nomination_video_desc: "Vous pouvez importer du contenu d'un utilisateur depuis YouTube ou Vimeo de votre pays.",
        tip_nomination_country: "Même pays requis",
        tip_nomination_country_desc: "Le contenu doit provenir d'un utilisateur de votre pays.",
        tip_nomination_required: "Vidéo obligatoire",
        tip_nomination_required_desc: "Les vidéos sont obligatoires pour les nominations.",
        tip_nomination_platforms: "Plateformes supportées",
        tip_nomination_platforms_desc: "YouTube et TikTok uniquement. Les YouTube Shorts, Instagram, Snapchat et Facebook ne sont pas acceptés.",
        tip_participation_content: "Utilisez votre propre contenu",
        tip_participation_content_desc: "Partagez vos propres photos et vidéos pour participer au concours.",
        tip_participation_media: "Médias requis",
        tip_participation_media_desc: "Vérifiez les exigences en matière d'images et de vidéos pour ce concours.",
        tip_participation_verification: "Vérification requise",
        tip_participation_verification_desc: "Assurez-vous que votre compte est vérifié pour participer.",
        tip_participation_quality: "Qualité du contenu",
        tip_participation_quality_desc: "Partagez votre meilleur contenu pour maximiser vos chances de gagner.",
        contest_type: {
          beauty: "Beauté",
          handsome: "Beau Gosse",
          latest_hits: "Derniers Hits",
          talent: "Talent",
          photography: "Photographie",
          fitness: "Fitness",
          fashion: "Mode",
          music: "Musique",
          dance: "Danse",
          cooking: "Cuisine",
          art: "Art",
          comics: "Comics",
          other: "Autre"
        },
        men: "Hommes",
        women: "Femmes",
        add_favorite: "Ajouter aux favoris",
        remove_favorite: "Retirer des favoris",
        added_to_favorites: "Ajouté aux favoris",
        removed_from_favorites: "Retiré des favoris",
        open: "Ouvert",
        open_for_candidacy: "Ouvert pour candidater",
        closed: "Fermé",
        submission_closed: "Le concours est fermé pour ce concours.",
        submission_closed_message: "La date limite de soumission est dépassée.",
        no_active_rounds: "Aucun round actif n'accepte les soumissions pour le moment.",
        requirements: "Conditions requises",
        kyc_required: "Vérification d'identité",
        kyc_required_description: "Seuls les participants avec une identité vérifiée peuvent participer à ce concours",
        visual_verification: "Photo de vous requise",
        visual_verification_description: "Une photo de vous est obligatoire pour participer à ce concours",
        voice_verification: "Vérification vocale",
        voice_verification_description: "Une vérification vocale est obligatoire pour participer à ce concours",
        brand_verification: "Marque vérifiée",
        brand_verification_description: "Seules les marques vérifiées peuvent participer à ce concours",
        content_verification: "Contenu original requis",
        content_verification_description: "Seul le contenu original est autorisé pour participer à ce concours",
        gender_restriction: "Restriction de genre",
        gender_restriction_female_description: "Seules les participantes féminines sont autorisées à participer à ce concours",
        gender_restriction_male_description: "Seuls les participants masculins sont autorisés à participer à ce concours",
        age_restriction: "Restriction d'âge",
        age_restriction_description: "Seuls les participants dans la tranche d'âge spécifiée peuvent participer",
        years: "ans",
        max_favorites: "5 favoris maximum",
        favorite_limit_reached: "Limite de 5 favoris atteinte",
        top_participants: "Top Participants",
        top_5_description: "Les 5 meilleurs participants du concours",
        view: "Voir",
        contestant: "participant",
        view_contestants: "Voir les participants",
        view_all_contestants: "Voir tous les participants",
        top_contestants: "Top Contestants",
        time_remaining: "Temps restant",
        time_unit_days: "j",
        time_unit_hours: "h",
        time_unit_minutes: "m",
        time_unit_seconds: "s",
        candidacy_ends: "Fin des candidatures",
        participation_ongoing: "Les candidatures sont encore ouvertes",
        vote: "Voter",
        view_details: "Voir les détails",
        already_voted: "Déjà voté",
        already_voted_message: "Vous avez déjà voté pour ce participant.",
        cannot_vote: "Vous ne pouvez pas voter pour ce participant",
        owner_cannot_vote: "Propriétaire, ne peut pas voter",
        own_cannot_vote: "Ma candidature, ne peut pas voter",
        restriction_different_city: "Ville différente",
        restriction_different_country: "Pays différent",
        restriction_different_region: "Région différente",
        restriction_different_continent: "Continent différent",
        restriction_own_contestant: "Votre candidature",
        restriction_not_authenticated: "Connexion requise",
        restriction_geographic: "Restriction géographique",
        restriction_user_not_found: "Utilisateur introuvable",
        restriction_different_city_desc: "Vous ne pouvez voter que pour les candidats de votre ville",
        restriction_different_country_desc: "Vous ne pouvez voter que pour les candidats de votre pays",
        restriction_different_region_desc: "Vous ne pouvez voter que pour les candidats de votre région",
        restriction_different_continent_desc: "Vous ne pouvez voter que pour les candidats de votre continent",
        restriction_own_contestant_desc: "Vous ne pouvez pas voter pour votre propre candidature",
        restriction_not_authenticated_desc: "Veuillez vous connecter pour voter",
        restriction_geographic_desc: "Vous ne pouvez pas voter en raison de restrictions géographiques",
        restriction_user_not_found_desc: "Utilisateur introuvable",
        vote_restriction: "Restriction de vote",
        votes: "votes",
        shares: "Partages",
        submission: "Soumission",
        voting: "Vote",
        tooltip_info: "Voir les détails et les conditions du concours",
        tooltip_time_remaining: "Temps restant avant la fin du concours",
        tooltip_gender_restriction_female: "Ce concours est réservé aux femmes uniquement",
        tooltip_gender_restriction_male: "Ce concours est réservé aux hommes uniquement",
        tooltip_level_city: "Concours au niveau de la ville",
        tooltip_level_country: "Concours au niveau national",
        tooltip_level_regional: "Concours au niveau régional",
        tooltip_level_continental: "Concours au niveau continental",
        tooltip_level_global: "Concours au niveau mondial",
        tooltip_open: "Le concours est actuellement ouvert. Vous pouvez concourir à ce concours.",
        tooltip_contestants: "Nombre de participants dans ce concours",
        tooltip_votes: "Nombre total de votes reçus",
        tooltip_participate: "Cliquez pour concourir à ce concours et soumettre votre candidature",
        tooltip_view_contestants: "Voir tous les participants de ce concours",
        tooltip_view_contestants_closed: "Le concours est fermé. Voir les participants du concours",
        tooltip_view_contestants_cannot_participate: "Vous ne pouvez pas concourir pour le moment. Voir les participants du concours",
        tooltip_closed: "Le concours est fermé. Les inscriptions ne sont plus acceptées.",
        tooltip_voting_open: "Le vote est actuellement ouvert. Vous pouvez voter pour les participants.",
        tooltip_rank: "Classement dans ce concours",
        tooltip_author: "Voir le profil du participant",
        tooltip_votes_author: "Votes reçus. Survolez pour voir la liste des votants.",
        start: "Début",
        end: "Fin",
        add_to_favorites: "Ajouter aux favoris",
        remove_from_favorites: "Retirer des favoris",
        share: "Partager",
        share_title: "Partager ce participant",
        share_description: "Partagez ce participant avec vos amis et votre réseau",
        share_link_label: "Lien de partage",
        copy: "Copier",
        copied: "Copié",
        share_natively: "Partager nativement",
        report: "Signaler",
        reactions: "Réactions",
        you_reacted: "Vous avez réagi",
        no_reactions: "Aucune réaction pour le moment",
        people_reacted: "personnes ont réagi",
        be_first_to_react: "Soyez le premier à réagir",
        participant: "Participant",
        rank: "Classement",
        reaction: "Réaction",
        search_contestant: "Rechercher un participant...",
        filtered_by_country: "Filtré par votre pays",
        no_contestants: "Aucun participant pour le moment",
        no_contestants_found: "Aucun participant trouvé",
        like: "J'aime",
        love: "J'adore",
        wow: "Wow",
        dislike: "Je n'aime pas",
        favorite: "Favori",
        comments_description: "Partagez vos pensées sur ce participant",
        add_comment_placeholder: "Ajouter un commentaire...",
        sending: "Envoi...",
        send: "Envoyer",
        no_comments: "Aucun commentaire pour le moment",
        cancel: "Annuler",
        mention_hint: "Tapez @ pour mentionner quelqu'un",
        edit: "Modifier",
        delete: "Supprimer",
        vote_error: "Erreur lors du vote. Veuillez réessayer.",
        voting_not_open: "Le vote n'est pas encore ouvert pour ce concours.",
        already_voted_error: "Déjà voté.",
        cannot_vote_own: "Vous ne pouvez pas voter pour votre propre candidature.",
        vote_success: "Vote enregistré avec succès!",
        vote_replaced: "Vote remplacé avec succès !",
        my_votes: "Mes votes",
        no_votes_yet: "Votez pour vos contestants préférés !",
        replace_vote_title: "Remplacer un vote",
        replace_vote_message: "Vous avez déjà 5 votes. Voulez-vous remplacer",
        replace_vote_position: "(5e position, 1 point) par ce participant ?",
        replace_vote_confirm: "Remplacer",
        max_votes_reached: "Vous avez atteint le maximum de 5 votes",
        empty_slot: "Emplacement vide",
        votes_remaining: "{n} vote(s) restant(s)",
        drag_to_reorder: "Glissez pour réordonner",
        vote_replaced: "Vote remplacé avec succès !",
        my_votes: "Mes votes",
        no_votes_yet: "Votez pour vos contestants préférés !",
        replace_vote_title: "Remplacer un vote",
        replace_vote_message: "Vous avez déjà 5 votes. Voulez-vous remplacer",
        replace_vote_position: "(5e position, 1 point) par ce participant ?",
        replace_vote_confirm: "Remplacer",
        max_votes_reached: "Vous avez atteint le maximum de 5 votes",
        empty_slot: "Emplacement vide",
        votes_remaining: "{n} vote(s) restant(s)",
        drag_to_reorder: "Glissez pour réordonner",
        vote_gender_restriction_male: "Ce concours est réservé aux participants masculins. Seules les participantes féminines peuvent voter.",
        vote_gender_restriction_female: "Ce concours est réservé aux participantes féminines. Seuls les participants masculins peuvent voter.",
        vote_gender_not_set: "Votre profil ne contient pas d'information de genre. Veuillez compléter votre profil pour voter dans ce concours.",
        my_applications: {
          title: "Mes Candidatures",
          description: "Consultez vos candidatures et votre classement",
          no_applications: "Vous n'avez pas encore de candidatures",
          browse_contests: "Parcourir les concours",
          status: "Statut",
          status_pending: "En attente",
          status_approved: "Approuvée",
          status_rejected: "Rejetée",
          rank: "Rang",
          view_details: "Voir les détails",
          view_page: "Voir la page",
          edit_not_available: "Édition non disponible pour ce contest",
          delete_not_available: "Suppression non disponible pour ce contest",
          delete_confirm_message: "Êtes-vous sûr de vouloir supprimer cette candidature ? Cette action ne peut pas être annulée.",
          details: "Détails",
          statistics: "Statistiques",
          total_shares: "Total de partages",
          shares_by_platform: "Partages par plateforme",
          no_shares: "Aucun partage pour le moment",
          contest: "Concours",
          date: "Date",
          media: "Médias",
          no_title: "Sans titre",
          user: "Utilisateur",
          media_alt: "Média",
          video_alt: "Vidéo",
          report: "Signaler",
          already_reported: "Déjà signalé"
        },
        suggest_contest: {
          title: "Suggérer un concours",
          description: "Proposez une idée de concours à notre équipe",
          button: "Suggérer un concours",
          name_label: "Nom du concours",
          name_placeholder: "Ex: Concours de beauté 2024",
          description_label: "Description",
          description_placeholder: "Décrivez votre idée de concours...",
          category_label: "Catégorie",
          category_placeholder: "Sélectionnez une catégorie",
          submit: "Envoyer la suggestion",
          submitting: "Envoi en cours...",
          success: "Votre suggestion a été envoyée avec succès !",
          success_message: "Merci pour votre suggestion. Notre équipe l'examinera et vous tiendra informé.",
          cancel: "Annuler",
          error: {
            name_required: "Le nom du concours est requis",
            category_required: "La catégorie est requise",
            submit_error: "Erreur lors de l'envoi de la suggestion",
            network_error: "Erreur de connexion. Vérifiez votre connexion internet.",
            server_error: "Erreur serveur. Veuillez réessayer plus tard."
          }
        },
        report_contestant: {
          title: "Signaler un participant",
          description: "Décrivez la raison de votre signalement. Notre équipe examinera votre demande.",
          contestant: "Participant",
          reason_label: "Raison du signalement",
          reason_placeholder: "Sélectionnez une raison",
          description_label: "Description détaillée",
          description_placeholder: "Décrivez en détail la raison de votre signalement (minimum 10 caractères)...",
          characters: "caractères",
          submit: "Envoyer le signalement",
          submitting: "Envoi en cours...",
          success: "Votre signalement a été envoyé avec succès !",
          cancel: "Annuler",
          reasons: {
            spam: "Spam",
            inappropriate: "Contenu inapproprié",
            harassment: "Harcèlement",
            fake: "Faux compte",
            copyright: "Violation de droits d'auteur",
            other: "Autre"
          },
          error: {
            reason_required: "La raison est requise",
            description_required: "La description est requise",
            description_min_length: "La description doit contenir au moins 10 caractères",
            submit_error: "Erreur lors de l'envoi du signalement",
            network_error: "Erreur de connexion. Vérifiez votre connexion internet.",
            server_error: "Erreur serveur. Veuillez réessayer plus tard."
          }
        },
        participation_form: {
          title: "Participer au concours",
          description: "Sélectionnez votre meilleure photo ou vidéo pour participer à ce concours",
          edit_title: "Modifier un Candidat",
          edit_description: "Mettez à jour les détails de votre soumission",
          nominate_title: "Nommer un Candidat",
          nominate_description: "Importez votre vidéo depuis YouTube ou TikTok",
          select_media: "Sélectionner votre média",
          drag_drop: "Glissez-déposez votre fichier ici",
          file_info: "ou cliquez pour sélectionner (Images: JPG, PNG, GIF | Vidéos: MP4, WebM | Max: 100MB)",
          submit: "Soumettre ma candidature",
          success: "Votre candidature a été soumise avec succès. Elle sera examinée par notre équipe.",
          success_title: "✅ Candidature soumise avec succès !",
          success_edit: "Votre candidature a été mise à jour avec succès.",
          already_participating: "ℹ️ Vous avez déjà une candidature pour ce concours. Vous ne pouvez soumettre qu'une seule candidature par concours.",
          edit_participation: "Modifier ma candidature",
          click_add_images: "Cliquez pour ajouter des images",
          preparing: "Préparation...",
          checking_files: "Vérification des fichiers...",
          uploading: "Upload en cours...",
          images_format: "Images",
          click_add_video: "Cliquez pour ajouter une vidéo",
          video_format: "Vidéo",
          cancel: "Annuler",
          error: {
            no_media_selected: "Veuillez sélectionner un fichier",
            invalid_file_type: "Type de fichier non supporté",
            file_too_large: "Le fichier est trop volumineux (max 100MB)",
            contest_not_found: "Concours non trouvé",
            submit_error: "Erreur lors de la soumission",
            gender_restriction_male: "Ce concours est réservé aux participants masculins uniquement.",
            gender_restriction_female: "Ce concours est réservé aux participantes féminines uniquement.",
            gender_not_set: "Votre profil ne contient pas d'information de genre. Veuillez compléter votre profil pour participer à ce concours.",
            already_submitted: "Vous avez déjà soumis une candidature pour ce concours.",
            submission_closed: "Les inscriptions sont fermées pour ce concours.",
            deadline_passed: "La date limite de soumission est dépassée."
          }
        }
      },
      favorites: {
        title: "Mes Favoris",
        description: "Consultez vos contests et candidats favoris",
        description_contestants: "Organisez vos contestants favoris par glisser-déposer",
        contests_tab: "Concours",
        contestants_tab: "Candidats",
        no_favorite_contests: "Vous n'avez pas encore de concours favoris",
        no_favorite_contestants: "Vous n'avez pas encore de candidats favoris",
        no_favorites_yet: "Aucun favori pour le moment",
        no_favorites_hint: "Ajoutez des contestants à vos favoris depuis la page d'un concours en cliquant sur l'étoile.",
        browse_contests: "Parcourir les concours"
      },
      myhigh5: {
        title: "MyHigh5",
        description: "Les 5 contestants pour lesquels vous avez voté",
        hint: "Votre premier vote est affiché en position 1, et votre vote le plus récent en position 5. Vous pouvez voter pour un maximum de 5 contestants.",
        no_votes: "Aucun vote",
        no_votes_description: "Vous n'avez pas encore voté pour des contestants. Explorez les concours pour voter!",
        explore_contests: "Explorer les concours",
        explore_more: "Explorer plus de concours",
        remaining_votes: "Vous pouvez encore voter pour {count} contestant(s)",
        votes_label: "votes",
        hint_dnd: "Glissez-déposez pour réorganiser vos votes. Le 1er reçoit 5 points, le 2ème 4 points, le 3ème 3 points, le 4ème 2 points et le 5ème 1 point. Les votes sont limités à 5 par season.",
        hint_tap:
          "Touchez la photo d’un candidat pour le sélectionner, puis touchez une autre photo pour le placer à ce rang. Touchez la même photo pour annuler.",
        tap_reorder_second: "Touchez une autre photo pour déplacer {name} à cette position.",
        tap_reorder: "Touchez pour sélectionner, puis une autre photo pour réorganiser",
        drag_reorder: "Glissez la photo de profil pour réorganiser votre High5",
        rank: "Rang",
        points: "Points",
        contestant: "Contestant",
        location: "Localisation",
        total_votes: "Votes totaux",
        vote_date: "Date du vote",
        order_saved: "Ordre sauvegardé !",
        order_error: "Erreur lors de la sauvegarde",
        points_legend: "Système de points",
        points_label: "points",
        active_tab: "Actifs",
        history_tab: "Historique",
        no_history: "Aucun historique",
        no_history_description: "Vous n'avez pas encore d'historique de votes.",
        inactive: "Terminé"
      },
      leaderboard: {
        title: "Classement des Sponsors",
        subtitle: "Les 10 meilleurs sponsors avec le plus de référents directs",
        mfm_subtitle: "Les 10 meilleurs sponsors MFM avec le plus de référents directs ayant acheté MFM",
        regular_tab: "Classement Général",
        mfm_tab: "Classement MFM",
        referrals: "Référents",
        benefit: "Bénéfice",
        champion: "Champion",
        no_data: "Aucun sponsor trouvé",
        info_title: "Comment fonctionne le classement ?",
        info_description: "Le classement est basé sur le nombre de référents directs (niveau 1) de chaque sponsor. Plus vous avez de référents directs, plus votre position dans le classement est élevée."
      }
    },
    hero: {
      badge: "Plateforme de concours #1 mondiale",
      title_line1: "Rejoignez la plus",
      title_line2: "grande communauté",
      title_line3: "de concours",
      subtitle: "Participez en tant que candidat, nommez votre candidat préféré dans votre pays, ou votez dans n'importe quel concours, et soyez récompensé tout en vous amusant.",
      description: "Participez en tant que candidat, nommez votre candidat préféré dans votre pays, ou votez dans n'importe quel concours, et soyez récompensé tout en vous amusant.",
      cta: "Commencer maintenant",
      demo: "Voir la démo",
      stats: {
        participants: "Participants actifs",
        contests: "Concours organisés",
        countries: "Pays représentés"
      },
      trust: {
        secure: "Sécurisé et certifié",
        support: "Support 24/7",
        free: "Gratuit à rejoindre"
      }
    },
    nav: {
      home: "Accueil",
      contests: "Concours",
      rankings: "Classements",
      community: "Communauté",
      about: "À propos",
      login: "Se connecter",
      register: "S'inscrire"
    },
    navigation: {
      home: "Accueil",
      landing: "Accueil",
      dashboard: "Tableau de bord",
      contests: "Concours",
      clubs: "Clubs",
      about: "À propos",
      contact: "Contact",
      login: "Se connecter",
      register: "S'inscrire",
      download_app: "Télécharger l'app"
    },
    header: {
      language: "Langue",
      theme: "Thème"
    },
    auth: {
      email: "Email",
      password: "Mot de passe",
      username: "Nom d'utilisateur",
      forgotPassword: "Mot de passe oublié ?",
      loginError: "Erreur de connexion",
      registerError: "Erreur d'inscription",
      referral_detected: "Code de parrainage détecté !",
      referral_bonus: "Vous avez été parrainé !",
      referral_code: "Code",
      login: {
        title: "Connexion",
        subtitle: "Connectez-vous à votre compte MyHigh5",
        email_placeholder: "Email ou nom d'utilisateur",
        password_placeholder: "Votre mot de passe",
        forgot_password: "Mot de passe oublié ?",
        loading: "Connexion...",
        submit: "Se connecter",
        no_account: "Pas encore de compte ?",
        register_link: "S'inscrire",
        errors: {
          required_fields: "Tous les champs sont obligatoires",
          invalid_credentials: "Email/nom d'utilisateur ou mot de passe incorrect",
          timeout: "Délai dépassé. Veuillez réessayer.",
          network_error: "Erreur de connexion. Vérifiez votre connexion internet.",
          service_unavailable: "Le service démarre. Veuillez patienter quelques instants et réessayer."
        }
      },
      register: {
        title: "Inscription",
        subtitle: "Créez votre compte MyHigh5 gratuitement",
        email_placeholder: "Votre adresse email",
        username_placeholder: "Nom d'utilisateur",
        username_hint: "Seules les lettres, chiffres et underscores sont autorisés",
        username_no_spaces_warning: "Caractères non autorisés",
        username_space_not_allowed: "Les espaces ne sont pas autorisés",
        password_requirements_title: "Le mot de passe doit contenir :",
        password_requirement_uppercase: "Une majuscule (A-Z)",
        password_requirement_lowercase: "Une minuscule (a-z)",
        password_requirement_number: "Un chiffre (0-9)",
        password_requirement_special: "Un caractère spécial (*_/@=)",
        password_placeholder: "Mot de passe",
        confirm_password_placeholder: "Confirmez le mot de passe",
        full_name_placeholder: "Nom complet",
        phone_placeholder: "Numéro de téléphone",
        referral_code_placeholder: "Code de parrainage (optionnel)",
        country: "Pays",
        country_placeholder: "Sélectionner un pays",
        city: "Ville",
        city_placeholder: "Saisissez votre ville",
        loading: "Inscription...",
        submit: "S'inscrire",
        have_account: "Déjà un compte ?",
        login_link: "Se connecter",
        terms_accept: "J'accepte les conditions d'utilisation",
        success_title: "Inscription réussie !",
        success_message: "Bienvenue ! Votre compte a été créé avec succès.",
        continue_button: "Se connecter",
        password_requirements_title: "Le mot de passe doit contenir :",
        password_requirement_uppercase: "Une majuscule (A-Z)",
        password_requirement_lowercase: "Une minuscule (a-z)",
        password_requirement_number: "Un chiffre (0-9)",
        password_requirement_special: "Un caractère spécial (*_/@=)",
        errors: {
          required_fields: "Tous les champs obligatoires doivent être remplis",
          password_mismatch: "Les mots de passe ne correspondent pas",
          password_min_length: "Le mot de passe doit contenir au moins 8 caractères",
          terms_required: "Vous devez accepter les conditions d'utilisation",
          email_exists: "Un utilisateur avec cet email existe déjà",
          username_exists: "Ce nom d'utilisateur est déjà pris",
          invalid_email: "Format d'email invalide",
          username_invalid_chars: "Seuls les lettres, chiffres et underscores sont autorisés",
          password_requirements: "Le mot de passe doit contenir une majuscule, une minuscule, un chiffre et un caractère spécial (*_/@=)",
          location_required: "Veuillez sélectionner votre pays et votre ville"
        }
      },
      verify_email: {
        no_token: "Token de vérification manquant",
        success: "Email vérifié avec succès",
        error: "Erreur lors de la vérification de l'email",
        verifying: "Vérification en cours...",
        please_wait: "Veuillez patienter pendant que nous vérifions votre email.",
        success_title: "Email vérifié !",
        redirecting: "Redirection vers la page de connexion...",
        error_title: "Erreur de vérification",
        invalid_token: "Token invalide ou expiré"
      },
      forgot_password: {
        title: "Mot de passe oublié ?",
        description: "Entrez votre adresse email et nous vous enverrons un lien pour réinitialiser votre mot de passe.",
        email_required: "L'email est requis",
        send_reset_link: "Envoyer le lien de réinitialisation",
        success: "Un email de réinitialisation a été envoyé",
        success_title: "Email envoyé !",
        success_message: "Si cet email existe dans notre système, vous recevrez un lien de réinitialisation de mot de passe.",
        check_spam: "Vérifiez votre dossier spam si vous ne recevez pas l'email.",
        remember_password: "Vous vous souvenez de votre mot de passe ?",
        error: "Erreur lors de l'envoi de l'email"
      },
      reset_password: {
        title: "Réinitialiser le mot de passe",
        description: "Entrez votre nouveau mot de passe ci-dessous.",
        no_token: "Token de réinitialisation manquant",
        password_required: "Le mot de passe est requis",
        password_min_length: "Le mot de passe doit contenir au moins 6 caractères",
        confirm_password_required: "La confirmation du mot de passe est requise",
        passwords_not_match: "Les mots de passe ne correspondent pas",
        new_password: "Nouveau mot de passe",
        confirm_password: "Confirmer le mot de passe",
        submit: "Réinitialiser le mot de passe",
        success: "Mot de passe réinitialisé avec succès",
        success_title: "Mot de passe réinitialisé !",
        success_message: "Votre mot de passe a été réinitialisé avec succès. Vous pouvez maintenant vous connecter.",
        redirecting: "Redirection vers la page de connexion...",
        error: "Erreur lors de la réinitialisation du mot de passe",
        invalid_token: "Token invalide ou expiré"
      }
    },
    common: {
      loading: "Chargement...",
      error: "Erreur",
      success: "Succès",
      network_error: "Erreur de connexion. Vérifiez votre connexion internet.",
      cancel: "Annuler",
      confirm: "Confirmer",
      continue: "Continuer",
      or: "ou",
      redirecting: "Redirection en cours...",
      please_wait: "Veuillez patienter...",
      back: "Retour",
      back_to_dashboard: "Retour au tableau de bord",
      previous: "Précédent",
      next: "Suivant",
      submitting: "Envoi en cours...",
      no_documents: "Aucun document",
      profile_setup: "Configuration du profil",
      profile_setup_description: "Complétez votre profil pour continuer",
      edit: "Éditer",
      delete: "Supprimer",
      deleting: "Suppression...",
      confirm_delete: "Confirmer la suppression",
      deleted_successfully: "Supprimé avec succès",
      likes: "Likes",
      comments: "Commentaires",
      search: "Rechercher",
      clear: "Effacer",
      optional: "optionnel",
      coming_soon: "Bientôt",
      welcome: "Bienvenue",
      access_denied: "Accès refusé",
      no_permission: "Vous n'avez pas les permissions pour accéder à cette page.",
      refresh: "Actualiser",
      view_more: "Voir plus",
      unknown: "Inconnu",
      load_more: "Charger plus",
      actions: "Actions"
    },
    affiliates: {
      grow_network: "Développez Votre Réseau",
      invite_friends: "Invitez des amis et gagnez des commissions sur leurs activités",
      invite_now: "Inviter Maintenant",
      title: "Programme d'Affiliation",
      your_link: "Votre Lien d'Affiliation",
      copy_link: "Copier le Lien",
      link_copied: "Lien copié !",
      share: "Partager",
      earnings: "Vos Gains",
      pending: "En Attente",
      paid: "Payé",
      referrals: "Filleuls",
    },
    profile_setup: {
      location: "Localisation",
      gender: "Genre",
      date_of_birth: "Date de Naissance",
      male: "Homme",
      female: "Femme",
      other: "Autre",
      prefer_not_to_say: "Préfère ne pas dire",
      first_name: "Prénom",
      first_name_placeholder: "Votre prénom",
      first_name_required: "Le prénom est requis",
      last_name: "Nom",
      last_name_placeholder: "Votre nom",
      last_name_required: "Le nom est requis",
      avatar: "Avatar",
      avatar_required: "L'avatar est requis",
      bio: "Bio",
      bio_placeholder: "Parlez un peu de vous...",
      bio_required: "La bio est requise",
      characters: "caractères",
      city_required: "La ville est requise",
      continent_required: "Le continent est requis",
      region_required: "La région est requise",
      country_required: "Le pays est requis",
      gender_required: "Le genre est requis",
      dob_required: "La date de naissance est requise",
      session_expired: "Session expirée",
      update_error: "Erreur lors de la mise à jour du profil",
      success: "Profil configuré avec succès!",
      continue: "Continuer",
      info: "Ces informations sont requises pour participer aux concours. Vous pourrez les modifier ultérieurement dans vos paramètres de profil.",
      click_upload: "Cliquez pour uploader",
      preparing: "Préparation...",
      checking_files: "Vérification des fichiers...",
      uploading: "Upload en cours...",
      images: "Images",
      upload_error: "Erreur d'upload"
    },
    settings: {
      title: "Paramètres",
      description: "Gérez vos informations personnelles et vos préférences",
      profile: "Profil",
      profile_short: "Photo, nom et bio",
      profile_description: "Modifiez votre photo, nom et biographie",
      location: "Localisation",
      location_short: "Pays et ville",
      location_description: "Définissez votre localisation géographique",
      demographics: "Identité",
      demographics_short: "Genre et âge",
      demographics_description: "Renseignez vos informations personnelles",
      continent: "Continent",
      region: "Région",
      country: "Pays",
      city: "Ville",
      current_location: "Localisation actuelle",
      location_locked_title: "Localisation verrouillée",
      location_locked_message: "Vous avez déjà participé à un concours. Votre localisation ne peut pas être modifiée.",
      save: "Enregistrer",
      remove: "Supprimer",
      profile_completion: "Profil complété",
      missing: "Manque",
      referral_code_label: "Code parrainage",
      admin: "Admin",
      verified: "Vérifié",
      verify_identity: "Vérifier mon identité",
      years: "ans",
      user: "Utilisateur",
      profile_photo: "Photo de profil",
      biography: "Biographie",
      password: {
        title: "Mot de passe",
        description: "Modifiez votre mot de passe pour sécuriser votre compte",
        current: "Mot de passe actuel",
        new: "Nouveau mot de passe",
        confirm: "Confirmer le nouveau mot de passe",
        current_required: "Le mot de passe actuel est requis",
        new_required: "Le nouveau mot de passe est requis",
        confirm_required: "La confirmation du mot de passe est requise",
        min_length: "Le mot de passe doit contenir au moins 6 caractères",
        mismatch: "Les mots de passe ne correspondent pas",
        same_password: "Le nouveau mot de passe doit être différent de l'ancien",
        session_expired: "Session expirée",
        success: "Mot de passe modifié avec succès",
        error: "Erreur lors du changement de mot de passe",
        saving: "Modification...",
        save: "Modifier le mot de passe",
        security_info: "Sécurité de votre compte",
        security_description: "Pour protéger votre compte, utilisez un mot de passe fort et unique.",
        min_6_chars: "6 caractères minimum",
        uppercase: "Une majuscule",
        lowercase: "Une minuscule",
        number: "Un chiffre"
      },
      password_short: "Sécurité du compte"
    },
    participation: {
      location: "Votre Localisation",
      category: "Catégorie",
      categoryPlaceholder: "Sélectionnez une catégorie",
      title: "Titre",
      title_placeholder: "Entrez le titre de votre candidature",
      description: "Description",
      descriptionPlaceholder: "Décrivez votre candidature, vos talents, vos réalisations...",
      characters: "caractères",
      media: "Médias (Images/Vidéos)",
      images: "Images",
      images_placeholder: "Cliquez pour ajouter des images",
      video: "Vidéo",
      video_placeholder: "Cliquez pour ajouter une vidéo",
      video_optional: "Vidéo (optionnel)",
      clickUpload: "Cliquez ou glissez vos fichiers",
      preparing: "Préparation...",
      checkingFiles: "Vérification des fichiers...",
      uploading: "Upload en cours...",
      imagesVideos: "Images et vidéos",
      uploadError: "Erreur d'upload",
      uploadedFiles: "Fichiers uploadés",
      submit: "Soumettre ma candidature",
      cancel: "Annuler",
      profile_incomplete_title: "⚠️ Profil incomplet",
      profile_incomplete_message: "Vous devez compléter votre profil avant de pouvoir participer aux concours. Veuillez renseigner votre nom, prénom, pays et ville.",
      complete_profile_button: "Compléter mon profil",
      kyc_notification: "⚠️ Votre identité n'a pas été vérifiée. Nous vous recommandons de compléter votre vérification KYC pour une meilleure expérience.",
      // URL import
      or: "ou",
      add_by_url: "Ajouter par URL",
      add_video_by_url: "Ajouter par URL",
      add: "Ajouter",
      image_url_placeholder: "https://exemple.com/image.jpg",
      video_url_placeholder: "https://youtube.com/watch?v=... ou https://exemple.com/video.mp4",
      invalid_video_url: "Lien non autorisé. Seuls YouTube et TikTok sont acceptés.",
      unsupported_platform: "Lien non autorisé",
      open_link: "Ouvrir le lien",
      view_on_tiktok: "Voir sur TikTok",
      view_on_youtube: "Voir sur YouTube",
      only_youtube_tiktok: "Seuls YouTube et TikTok sont acceptés",
      invalid_url: "URL vidéo non valide",
      video_platform_not_allowed: "Plateforme vidéo non acceptée. Seuls YouTube et TikTok sont supportés.",
      video_file_not_allowed: "Les fichiers vidéo ne sont pas autorisés. Veuillez utiliser une URL YouTube ou TikTok.",
      youtube_shorts_not_allowed: "Les YouTube Shorts ne sont pas autorisés. Veuillez utiliser une vidéo YouTube standard.",
      tiktok_preview_unavailable: "Aperçu indisponible — regardez sur TikTok",
      watch_on_tiktok: "Regarder sur TikTok",
      url_required: "URL requise",
      invalid_url: "URL invalide",
      max_images_reached: "Nombre maximum d'images atteint",
      image_added: "Image ajoutée",
      video_added: "Vidéo ajoutée",
      // Media requirements
      media_requirements: "Exigences média",
      images_required: "Images",
      video_required: "Vidéo obligatoire",
      video_required_title: "Vidéo *",
      // New labels
      content_title: "Titre du contenu",
      content_title_placeholder: "Entrez le titre du contenu (minimum 10 caractères)",
      content_description: "Description du contenu",
      content_description_placeholder: "Entrez la description du contenu (20-50 caractères)",
      content_image: "Image du contenu",
      content_video_required: "Vidéo du contenu *",
      content_video_optional: "Vidéo du contenu (optionnel)",
      min_characters: "Minimum",
      important_errors: "Erreurs importantes à corriger",
      // Nominator location fields
      nominator_location: "Localisation du candidat",
      nominator_location_description: "Veuillez indiquer la localisation de la personne que vous nominez.",
      nominator_country: "Pays",
      nominator_country_note: "Le pays doit correspondre à votre pays de profil. Vous ne pouvez nommer que des candidats de votre propre pays.",
      select_country: "Sélectionnez un pays",
      nominator_city: "Ville",
      nominator_city_placeholder: "Entrez le nom de la ville",
      select_city: "Sélectionnez une ville",
      select_country_first: "Sélectionnez d'abord un pays",
      ad_revenue_warning: "Attention : Vous ne serez pas rémunéré sur les revenus publicitaires générés par votre contenu si nous détectons que le contenu ne provient pas de votre pays.",
      // Stepper
      step_info: "Informations",
      step_media: "Médias",
      step_review: "Vérification",
      time_remaining: "Temps de participation restant",
      deadline: "Date limite",
      submission_period_ended: "La période de soumission est terminée",
      review_title: "Vérifiez votre candidature",
      supported_platforms: "Plateformes supportées",
      unrecognized_video_link: "Lien vidéo non reconnu",
      // Errors
      errors: {
        content_title_required: "Titre du contenu",
        content_title_min_length: "Le titre du contenu doit contenir au moins 5 caractères",
        content_title_max_length: "Le titre du contenu ne doit pas dépasser 5 caractères",
        content_description_required: "Description du contenu",
        content_description_min_length: "La description du contenu doit contenir au moins 20 caractères",
        content_description_max_length: "La description du contenu ne doit pas dépasser 50 caractères",
        content_image_required: "Image du contenu",
        at_least_one_image: "Au moins une image est requise",
        content_video_required: "Vidéo du contenu",
        video_required_for_contest: "Une vidéo est requise pour ce concours",
        fill_all_fields: "Veuillez remplir tous les champs requis avant de soumettre",
        nominator_country_required: "Le pays du candidat est requis"
      }
    },
    moderation: {
      content_rejected: "⚠️ Contenu rejeté par la modération",
      adult_content: "Contenu adulte détecté",
      violence_detected: "Contenu violent détecté",
      gore_detected: "Contenu gore/sanglant détecté",
      weapons_detected: "Arme détectée",
      offensive_content: "Contenu offensant détecté",
      ownership_failed: "La vérification de propriété a échoué",
      face_mismatch: "Le visage ne correspond pas à votre vérification",
      analyzing: "Analyse du contenu en cours...",
      approved: "Contenu approuvé",
      rejected: "Contenu rejeté"
    },
    features: {
      title: "Fonctionnalités Exceptionnelles",
      subtitle: "Découvrez tout ce qui rend MyHigh5 une plateforme de concours en ligne mondiale unique et passionnante.",
      items: {
        multi_level: {
          title: "Concours Multi-Niveaux",
          description: "Participez à des compétitions locales, nationales et internationales avec un système de progression unique."
        },
        financial_rewards: {
          title: "Récompenses Financières",
          description: "Recevez des commissions d'affiliation sur les revenus générés par votre réseau de parrainage, jusqu'à 10 générations."
        },
        international_reach: {
          title: "Portée Internationale",
          description: "Vos talents peuvent être découverts et appréciés par une audience mondiale diversifiée."
        },
        innovative_voting: {
          title: "Vote Innovant",
          description: "Système de vote équitable et transparent avec classement en temps réel."
        },
        varied_categories: {
          title: "Catégories Variées",
          description: "Trouvez les catégories de concours qui vous passionnent. Recommandez les catégories manquantes que vous aimeriez voir ajoutées."
        }
      }
    },
    testimonials: {
      title: "Ce que disent nos utilisateurs",
      favorites: {
        title: "Mes Favoris",
        description: "Consultez vos contests et candidats favoris",
        description_contestants: "Organisez vos contestants favoris par glisser-déposer",
        contests_tab: "Concours",
        contestants_tab: "Candidats",
        no_favorite_contests: "Vous n'avez pas encore de concours favoris",
        no_favorite_contestants: "Vous n'avez pas encore de candidats favoris",
        no_favorites_yet: "Aucun favori pour le moment",
        no_favorites_hint: "Ajoutez des contestants à vos favoris depuis la page d'un concours en cliquant sur l'étoile.",
        browse_contests: "Parcourir les concours"
      },
      myhigh5: {
        title: "MyHigh5",
        description: "Les 5 contestants pour lesquels vous avez voté",
        hint: "Votre premier vote est affiché en position 1, et votre vote le plus récent en position 5. Vous pouvez voter pour un maximum de 5 contestants.",
        no_votes: "Aucun vote",
        no_votes_description: "Vous n'avez pas encore voté pour des contestants. Explorez les concours pour voter!",
        explore_contests: "Explorer les concours",
        explore_more: "Explorer plus de concours",
        remaining_votes: "Vous pouvez encore voter pour {count} contestant(s)",
        votes_label: "votes",
        hint_dnd: "Glissez-déposez pour réorganiser vos votes. Le 1er reçoit 5 points, le 2ème 4 points, le 3ème 3 points, le 4ème 2 points et le 5ème 1 point. Les votes sont limités à 5 par season.",
        rank: "Rang",
        points: "Points",
        contestant: "Contestant",
        location: "Localisation",
        total_votes: "Votes totaux",
        vote_date: "Date du vote",
        order_saved: "Ordre sauvegardé !",
        order_error: "Erreur lors de la sauvegarde",
        points_legend: "Système de points",
        points_label: "points"
      },
      subtitle: "Rejoignez des milliers de participants satisfaits qui ont transformé leur passion en succès.",
      cta: "Rejoignez des milliers de participants satisfaits",
      users: "+1M utilisateurs",
      items: {
        marie: {
          name: "Marie Dubois",
          text: "MyHigh5 m'a permis de découvrir mon talent et de rencontrer une communauté incroyable. J'ai gagné 3 concours cette année !",
          role: "Gagnante Concours Beauté",
          rating: 5,
          location: "Paris, France"
        },
        jean: {
          name: "Jean Martin",
          text: "L'interface est intuitive et les concours sont variés. C'est devenu ma plateforme préférée pour exprimer ma créativité.",
          role: "Participant Actif",
          rating: 5,
          location: "Lyon, France"
        },
        sophie: {
          name: "Sophie Laurent",
          text: "Grâce au programme d'affiliation, j'ai créé une source de revenus supplémentaire tout en m'amusant.",
          role: "Ambassadrice MyHigh5",
          rating: 5,
          location: "Marseille, France"
        },
        sarah_m: {
          name: "Sarah Martin",
          text: "Une expérience incroyable ! J'ai découvert ma passion pour la photographie grâce aux concours MyHigh5.",
          role: "Photographe Amateur",
          rating: 5,
          location: "Toulouse, France"
        },
        carlos_r: {
          name: "Carlos Rodriguez",
          text: "La communauté est fantastique et très encourageante. Mes talents de danse ont été reconnus internationalement !",
          role: "Danseur Professionnel",
          rating: 5,
          location: "Madrid, Espagne"
        },
        emma_l: {
          name: "Emma Laurent",
          text: "MyHigh5 m'a donné la confiance de partager mes créations. Maintenant, j'ai ma propre boutique en ligne !",
          role: "Artiste Créatrice",
          rating: 5,
          location: "Bruxelles, Belgique"
        }
      }
    },
    cta: {
      title: "Prêt à commencer votre aventure ?",
      subtitle: "Rejoignez des millions de participants et découvrez votre potentiel dès aujourd'hui.",
      button: "Créer mon compte gratuit",
      features: {
        instant: "Inscription instantanée",
        global: "Communauté mondiale",
        secure: "100% sécurisé",
        free_contests: "Concours gratuits",
        active_community: "Communauté active",
        real_rewards: "Vraies récompenses"
      },
      trust: {
        instant: "Inscription en 30 secondes",
        secure: "Aucune carte de crédit requise",
        support: "Support 24/7"
      }
    },
    landing: {
      ways_to_earn: {
        badge: "Gagnez de l'argent",
        title: "Différentes façons de gagner",
        subtitle: "Rejoignez notre programme d'affiliation et gagnez des commissions sur plusieurs sources de revenus",
        kyc_payments: {
          title: "Paiements KYC",
          description: "Gagnez des commissions lorsque les membres de votre réseau complètent leur vérification KYC",
          commission: "10% sur le niveau 1, 1% sur les niveaux 2-10"
        },
        founding_membership: {
          title: "Adhésion Fondateur",
          description: "Gagnez des commissions lorsque les membres de votre réseau de parrainage rejoignent le Club des Membres Fondateurs ou paient les frais d'adhésion annuels.",
          commission: "10% sur le niveau 1, 1% sur les niveaux 2-10"
        },
        annual_membership: {
          title: "Cotisation Annuelle",
          description: "Gagnez des commissions lorsque les Membres Fondateurs paient leur cotisation annuelle.",
          commission: "10% sur le niveau 1, 1% sur les niveaux 2-10"
        },
        club_memberships: {
          title: "Adhésions aux clubs",
          description: "Gagnez des commissions sur les frais d'adhésion aux clubs payants. Le site ajoute une majoration de 20% aux frais spécifiés par le propriétaire du club, dont 10% sont versés au niveau 1, et 1% à chacun des niveaux 2 à 10.",
          commission: "10% sur le niveau 1, 1% sur les niveaux 2-10"
        },
        shop_purchases: {
          title: "Achats en boutique",
          description: "Gagnez des commissions sur les achats de contenu numérique dans la boutique MyHigh5. Le site ajoute une majoration de 20% aux frais spécifiés par le propriétaire du club, dont 10% sont versés au niveau 1, et 1% à chacun des niveaux 2 à 10.",
          commission: "10% sur le niveau 1, 1% sur les niveaux 2-10"
        },
        ad_revenue: {
          title: "Partage des revenus publicitaires",
          description: "Les participants aux concours gagnent 40% des revenus publicitaires générés sur leurs pages de concours. Leurs parrains de niveau 1 gagnent 5%, et les niveaux 2 à 10 gagnent 1% chacun. Les membres qui nomment des candidats gagnent 10% des revenus publicitaires générés par leurs candidats nommés. Leurs parrains de niveau 1 gagnent 2.5%, et les niveaux 2 à 10 gagnent 1% chacun.",
          commission: "Participants : 40% pour soi, 5% pour le niveau 1, 1% pour chacun des niveaux 2 à 10.\nMembres qui nomment : 10% pour soi, 2.5% pour le niveau 1, 1% pour chacun des niveaux 2 à 10."
        },
        ad_campaigns: {
          title: "Page des Sponsors du Site Web",
          description: "Les parrains de niveau 1 gagnent une commission de 10%, et les niveaux 2 à 10 gagnent 1% chacun.",
          commission: "10% sur le niveau 1, 1% sur les niveaux 2-10"
        }
      },
      faq: {
        badge: "Questions fréquentes",
        title: "Questions fréquentes",
        subtitle: "Trouvez les réponses aux questions les plus courantes sur MyHigh5",
        question_1: "Comment puis-je gagner de l'argent sur MyHigh5 ?",
        answer_1: "Vous pouvez gagner de l'argent de plusieurs façons : en participant aux concours, en nommant des candidats, en rejoignant le programme d'affiliation pour gagner des commissions sur les membres que vous référez, et en devenant membre fondateur pour participer aux pools de revenus et de profits.",
        question_2: "Comment fonctionne le programme d'affiliation ?",
        answer_2: "• Paiements de frais de vérification :\n  Vous gagnez une commission de 10% sur les paiements effectués par vos parrainages directs, et une commission de 1% sur les paiements effectués par chacun de vos parrainages indirects du niveau 2 au niveau 10.\n\n• Revenus publicitaires (Candidats participants) :\n  Les candidats participants reçoivent 40% des revenus publicitaires générés sur leurs pages de concours. Le parrain direct d'un candidat participant reçoit 5%, et chaque parrain indirect du niveau 2 au niveau 10 reçoit 1%.\n\n• Revenus publicitaires (Membres qui nomment) :\n  Les membres qui nomment reçoivent 10% des revenus publicitaires générés sur les pages de concours de leurs candidats nommés, 2.5% des revenus publicitaires générés sur les pages de concours des candidats nommés par leurs parrainages directs, et 1% des revenus publicitaires générés sur les pages de concours des candidats nommés par chacun de leurs parrainages indirects du niveau 2 au niveau 10.\n\n• Revenus publicitaires (Clubs) :\n  Les propriétaires de clubs reçoivent 20% des revenus publicitaires générés sur leurs pages de club ou de fans. Le parrain direct d'un propriétaire de club reçoit 5%, et chaque parrain indirect du niveau 2 au niveau 10 reçoit 0.5%.\n\n• Frais d'adhésion aux clubs :\n  MyHigh5 applique une majoration de 20% aux frais d'abonnement sélectionnés par le membre. De cette majoration, 10% est versé au parrain direct du payeur, et 1% est versé à chaque parrain indirect du niveau 2 au niveau 10.\n\n• Emplacements sur la page des Sponsors du Site Web :\n  Pour les emplacements payés sur la page des Sponsors du Site Web, 10% est versé au parrain de niveau 1, et 1% est versé à chacun des parrains des niveaux 2 à 10.",
        question_3: "Qu'est-ce que le statut de Membre Fondateur ?",
        answer_3: "Le statut de Membre Fondateur (MFM) est une opportunité limitée qui nécessite la vérification du compte et le paiement de frais d'adhésion de 100$ et d'une cotisation annuelle de club de 50$ pour les 1 000 premiers MFM, et de frais d'adhésion de 200$ et d'une cotisation annuelle de club de 200$ par la suite. Les emplacements MFM cesseront d'exister une fois que le nombre total de MFM atteindra 10 000. Les Membres Fondateurs participent à des pools de commissions mensuelles équivalant à 5% des revenus nets et à un pool de profits annuels équivalant à 10% des profits après impôts, alloués en fonction de la proportion de leurs parrainages vérifiés de niveau 1 par rapport au nombre total de parrainages vérifiés de niveau 1.",
        question_4: "Comment puis-je participer aux concours ?",
        answer_4: "Pour participer aux concours, vous devez créer un compte gratuit, compléter votre profil, et soumettre votre candidature avec des photos ou vidéos selon les exigences du concours. Certains concours peuvent nécessiter une vérification KYC.",
        question_5: "Les concours sont-ils gratuits ?",
        answer_5: "Oui. La participation aux concours est gratuite, mais votre compte doit être vérifié car nous devons faire correspondre le contenu de votre participation à votre identité vérifiée. Vous n'avez pas besoin de vérifier votre compte pour nommer des candidats.",
        question_6: "Comment puis-je retirer mes gains ?",
        answer_6: "Vous pouvez retirer vos gains via votre portefeuille dans le tableau de bord. Les paiements sont traités mensuellement, avec un seuil minimum de paiement de 100$. Les méthodes de paiement incluent le virement bancaire, PayPal, ou la cryptomonnaie."
      },
      download_app: {
        badge: "Application mobile",
        title: "Téléchargez l'application MyHigh5",
        subtitle: "Participez aux concours, votez et gagnez de l'argent où que vous soyez avec notre application mobile",
        scan_qr: "Scannez pour télécharger",
        download_on: "Télécharger sur",
        app_store: "App Store",
        available_on: "Disponible sur",
        google_play: "Google Play",
        access_24_7: "Accès continu",
        free: "Gratuit"
      }
    },
    footer: {
      description: "La plateforme de concours la plus populaire au monde. Participez, votez et gagnez dans des compétitions passionnantes.",
      copyright: " 2024 MyHigh5. Tous droits réservés.",
      newsletter: {
        title: "Restez informé des nouveaux concours",
        subtitle: "Recevez les dernières actualités et opportunités directement dans votre boîte mail.",
        placeholder: "Votre adresse email",
        subscribe: "S'abonner",
        terms: "En vous inscrivant, vous acceptez nos conditions d'utilisation et notre politique de confidentialité."
      },
      brand: {
        countries: "Disponible dans 200+ pays",
        support: "Support 24/7",
        email: "infos@myhigh5.com"
      },
      quick_links: {
        title: "Liens Rapides",
        about: "À propos",
        contests: "Concours",
        how_it_works: "Comment ça marche",
        affiliate: "Programme d'affiliation",
        support: "Support"
      },
      categories: {
        title: "Catégories",
        beauty: "Concours Beauté",
        handsome: "Concours Charme",
        latest_hits: "Derniers Hits",
        pets: "Animaux de Compagnie",
        sports_clubs: "Clubs Sportifs",
        no_categories: "Aucune catégorie disponible"
      },
      legal: {
        title: "Légal",
        privacy: "Politique de confidentialité",
        terms: "Conditions d'utilisation",
        cookies: "Politique des cookies",
        gdpr: "Conformité RGPD"
      }
    },
    contestant_detail: {
      about: "À propos",
      gallery: "Galerie",
      photos: "Photos",
      images: "Images",
      videos: "Vidéos",
      votes: "Votes",
      rank: "Rang",
      contest_info: "Concours",
      candidate_info: "Candidature",
      title: "Titre",
      participants: "Participants",
      registered_on: "Inscrit le",
      status: "Statut",
      qualified: "✓ Qualifié",
      pending: "⏳ En attente",
      confirm_vote: "Confirmer votre vote",
      vote_confirmation: "Êtes-vous sûr de vouloir voter pour",
      are_you_sure: "?",
      cancel: "Annuler",
      vote: "Voter",
      voted: "Voté",
      voting: "Votage...",
      cover_image: "Image de couverture",
      vote_error: "Erreur lors du vote. Veuillez réessayer.",
      vote_success: "Vous avez voté avec succès! ✨",
      add_reaction: "Ajouter une réaction",
      react: "Réagir",
      like: "J'aime",
      love: "Adoré",
      wow: "Wow",
      dislike: "Pas aimé",
      vote_history: "Historique des votes",
      no_votes: "Aucun vote pour le moment",
      voted_for: "A voté pour",
      reaction: "Réaction",
      comment: "Commentaire",
      date: "Date",
      comments: "Commentaires",
      add_comment: "Ajouter un commentaire",
      comment_placeholder: "Écrivez votre commentaire...",
      comment_on_photo: "Commenter cette photo",
      comment_on_video: "Commenter cette vidéo",
      comment_on_contest: "Commenter ce concours",
      no_comments: "Aucun commentaire pour le moment",
      comment_posted: "Commentaire posté avec succès! ✨",
      comment_error: "Erreur lors de la publication du commentaire",
      comments_count: "Commentaires",
      reply: "Répondre",
      reply_placeholder: "Écrivez votre réponse...",
      like_comment: "J'aime",
      media_preview: "Aperçu du média",
      close: "Fermer",
      of: "de",
      contestant_label: "Participant",
      nominator_label: "Nominateur",
      nominated_for: "Nominé pour :",
      contest_rank_label: "Classement",
      description_section: "Description",
      candidacy_id: "ID de candidature",
      season_label: "Saison",
      entry_fallback_title: "Candidature",
      full_description: "Description complète"
    },
    dashboard: {
      welcome: "Bienvenue",
      subtitle: "Découvrez votre tableau de bord personnalisé",
      search: {
        placeholder: "Rechercher...",
        title: " Recherche",
        description: "Trouvez des concours, des participants, des clubs et des produits",
        no_results: "Aucun résultat trouvé",
        start_typing: "Commencez à taper pour rechercher...",
        contest: "Concours",
        contestant: "Participant",
        club: "Club",
        product: "Produit",
        recent_searches: "Recherches récentes",
        no_history: "Aucune recherche récente."
      },
      nav: {
        home: "Accueil",
        overview: "Aperçu",
        contests: "Concours",
        my_applications: "Mes Candidatures",
        clubs: "Clubs",
        myhigh5: "MyHigh5",
        favorites: "Favoris",
        search: "Recherche",
        pages: "Pages",
        wallet: "Portefeuille",
        affiliates: "Affiliés",
        commissions: "Commissions",
        leaderboard: "Classement",
        prize: "Prix",
        shop: "Boutique",
        main: "Principal",
        competitions: "Compétitions",
        business: "Affaires",
        resources: "Ressources",
        founding_member: "Founding Membership",
        affiliate_program: "Programme d'Affiliation",
        affiliate_agreement: "Accord d'Affiliation",
        account: "Compte",
        settings: "Paramètres",
        admin: "Administration",
        admin_panel: "Panneau Admin",
        admin_panel_desc: "Gérer la plateforme",
        notifications: "Notifications",
        notifications_desc: "Voir toutes vos notifications"
      },
      stats: {
        contests: "Mes Concours",
        clubs: "Mes Clubs",
        favorites: "Mes Favoris",
        points: "Mes Points"
      },
      analytics: {
        hello: "Bonjour",
        overview: "Voici un aperçu de vos performances",
        performance: "Performance",
        affiliates: "Affiliés",
        total_votes: "Votes",
        likes: "J'aime",
        comments: "Commentaires",
        total_views: "Vues",
        reactions: "Réactions",
        direct_affiliates: "Affiliés Directs",
        total_network: "Réseau Total",
        commissions: "Commissions",
        conversion_rate: "Taux Conversion",
        contest_performance: "Performance par Concours",
        contest_performance_desc: "Votes et engagement de vos candidatures",
        reactions_distribution: "Réactions",
        reactions_distribution_desc: "Distribution par type",
        weekly_activity: "Activité Hebdomadaire",
        weekly_activity_desc: "Votes et vues cette semaine",
        network_growth: "Croissance du Réseau",
        network_growth_desc: "Évolution de vos affiliés",
        monthly_commissions: "Commissions Mensuelles",
        monthly_commissions_desc: "Revenus générés par votre réseau",
        active_contests: "Concours Actifs",
        best_ranking: "Meilleur Classement",
        engagement: "Engagement",
        this_month: "Ce mois",
        total: "Total",
        last_7_days: "7 jours",
        view_stats: "Voir les statistiques",
        statistics: "Statistiques",
        days: {
          monday: "Lundi",
          tuesday: "Mardi",
          wednesday: "Mercredi",
          thursday: "Jeudi",
          friday: "Vendredi",
          saturday: "Samedi",
          sunday: "Dimanche",
          mon: "Lun",
          tue: "Mar",
          wed: "Mer",
          thu: "Jeu",
          fri: "Ven",
          sat: "Sam",
          sun: "Dim"
        },
        months: {
          january: "Janvier",
          february: "Février",
          march: "Mars",
          april: "Avril",
          may: "Mai",
          june: "Juin",
          july: "Juillet",
          august: "Août",
          september: "Septembre",
          october: "Octobre",
          november: "Novembre",
          december: "Décembre",
          jan: "Jan",
          feb: "Fév",
          mar: "Mar",
          apr: "Avr",
          may_short: "Mai",
          jun: "Juin",
          jul: "Juil",
          aug: "Août",
          sep: "Sep",
          oct: "Oct",
          nov: "Nov",
          dec: "Déc"
        }
      },
      wallet: {
        title: "Mon Portefeuille",
        subtitle: "Gérez vos revenus et transactions",
        available_balance: "Solde disponible",
        pending_balance: "En attente",
        pending_description: "Fonds en cours de validation",
        total_earnings: "Gains totaux",
        since_registration: "Depuis votre inscription",
        this_month: "Ce mois",
        history: "Historique",
        withdraw: "Retirer",
        recent_transactions: "Transactions récentes",
        all_transactions: "Toutes les transactions",
        transactions_subtitle: "Historique complet de vos transactions",
        see_all: "Voir tout",
        completed: "Payé",
        approved: "Approuvé",
        pending: "En attente",
        failed: "Échoué",
        expired: "Expiré",
        commission: "Commission",
        purchase: "Achat",
        all: "Tout",
        commissions: "Commissions",
        purchases: "Achats",
        filter_by_type: "Filtrer par type",
        export: "Exporter",
        no_transactions: "Aucune transaction",
        no_transactions_desc: "Vous n'avez pas encore de transactions",
        pay: "Payer",
        invoice: "Facture",
        download_invoice: "Télécharger la facture",
        buy_service: "Acheter un service"
      },
      affiliates: {
        title: "Programme Affilié",
        subtitle: "Parrainez et gagnez des commissions",
        invite: "Inviter",
        total_affiliates: "Total affiliés",
        direct_affiliates: "Affiliés directs",
        total_commissions: "Commissions",
        conversion_rate: "Taux conversion",
        your_referral_link: "Votre lien de parrainage",
        your_referral_links: "Vos liens de parrainage",
        link_register: "Lien d'inscription",
        link_home: "Lien page d'accueil",
        link_contestants: "Lien page concours",
        your_code: "Votre code",
        copy: "Copier",
        copied: "Copié !",
        share: "Partager",
        view_links: "Voir les liens",
        share_description: "Partagez vos liens et gagnez des commissions sur chaque inscription",
        links_description: "Copiez et partagez ces liens pour parrainer de nouveaux utilisateurs",
        your_sponsor: "Votre parrain",
        no_sponsor: "Aucun parrain",
        commission_tiers: "Niveaux de commission",
        commission_description: "Découvrez nos 10 niveaux de commission",
        view_commissions: "Voir les détails",
        total_potential: "Total potentiel",
        max_commission: "Commission maximale sur 10 niveaux",
        level: "Niveau",
        direct_referrals: "Parrainages directs",
        second_level: "Second niveau",
        third_level: "Troisième niveau",
        your_affiliates: "Vos affiliés",
        see_all: "Voir tout",
        active: "Actif",
        joined: "Rejoint le",
        earnings: "Gains générés",
        no_affiliates: "Aucun affilié pour le moment",
        start_inviting: "Commencez à inviter des amis pour gagner des commissions",
        invite_friends: "Inviter des amis",
        ten_levels: "10 niveaux de commission",
        commission: "Commission",
        no_commission: "Aucune commission",
        kyc_pending: "KYC en cours",
        commission_rate: "10% sur les paiements KYC",
        commission_structure: "Structure des commissions KYC",
        all_kyc_statuses: "Tous KYC",
        kyc_status_label: "Statut KYC",
        kyc_none: "Non initié",
        kyc_in_progress: "En cours",
        kyc_approved: "Vérifié",
        kyc_rejected: "Rejeté",
        kyc_expired: "Expiré",
        kyc_requires_review: "À revoir",
        kyc_verified: "KYC Vérifiés",
        direct_referrals: "Directs (Niv. 1)",
        indirect_referrals: "Indirects (Niv. 2-10)",
        direct_tooltip_title: "Referrals Directs",
        direct_tooltip_desc: "Utilisateurs que vous avez directement parrainés (niveau 1). Vous gagnez 10% de commission sur leurs paiements KYC.",
        indirect_tooltip_title: "Referrals Indirects",
        indirect_tooltip_desc: "Utilisateurs parrainés par vos filleuls (niveaux 2-10). Vous gagnez 1% de commission sur leurs paiements KYC.",
        earned: "Gagné",
        total_tooltip_title: "Total Affiliés",
        total_tooltip_desc: "Nombre total de personnes dans votre réseau d'affiliation, tous niveaux confondus (1 à 10).",
        active_tooltip_title: "Affiliés Actifs",
        active_tooltip_desc: "Utilisateurs ayant un compte actif et pouvant générer des commissions.",
        kyc_verified_tooltip_title: "KYC Vérifiés",
        kyc_verified_tooltip_desc: "Affiliés ayant complété avec succès la vérification d'identité (KYC approuvé).",
        commissions_tooltip_title: "Total Commissions",
        commissions_tooltip_desc: "Somme de toutes les commissions gagnées grâce à votre réseau d'affiliation.",
        col_affiliate_hint: "Informations sur le membre de votre réseau",
        col_level_hint: "Niveau 1 = direct (10%), Niveaux 2-10 = indirect (1%)",
        col_kyc_hint: "Statut de vérification d'identité (commission perçue si approuvé)",
        col_referrals_hint: "Nombre de personnes parrainées par cet affilié",
        col_earnings_hint: "Commission que vous avez gagnée grâce à cet affilié",
        col_status_hint: "Statut du compte utilisateur (actif ou inactif)",
        levels: "Niveaux",
        direct_commission: "Commission directe",
        indirect_commission: "Commissions indirectes",
        indirect_description: "Gagnez 1% sur chaque niveau de votre réseau, jusqu'au 10ème niveau.",
        cookie_tracking: "Tracking par cookies : 30 jours",
        all_affiliates: "Tous les affiliés",
        affiliates_found: "affiliés trouvés",
        search_placeholder: "Rechercher par nom ou email...",
        all_levels: "Tous les niveaux",
        all_statuses: "Tous les statuts",
        inactive: "Inactif",
        affiliate: "Affilié",
        referrals_count: "Parrainages",
        status: "Statut",
        total_referrals: "Total parrainages",
        no_results: "Aucun résultat",
        try_different_filters: "Essayez avec des filtres différents",
        showing: "Affichage",
        of: "sur",
        // Invitations
        pending_invitations: "En attente",
        invite_friend: "Inviter un ami",
        invite_description: "Envoyez une invitation par email pour parrainer vos amis",
        email_address: "Adresse email",
        personal_message: "Message personnalisé",
        message_placeholder: "Salut ! Rejoins-moi sur MyHigh5...",
        send_invitation: "Envoyer l'invitation",
        sending: "Envoi en cours...",
        share_link: "Partager votre lien",
        code_label: "Code",
        link_copied: "Lien copié !",
        invite_sent_success: "Invitation envoyée avec succès !",
        invite_error: "Erreur lors de l'envoi de l'invitation",
        invite_email_required: "Veuillez entrer un email",
        pending: "En attente",
        sent_on: "Envoyé le",
        cancel: "Annuler",
        invitation_cancelled: "Invitation annulée",
        no_pending: "Aucune invitation en attente",
        send_invitation_desc: "Envoyez des invitations à vos amis pour les parrainer",
        copy_error: "Erreur lors de la copie",
        cancel_error: "Erreur lors de l'annulation"
      },
      commissions: {
        title: "Mes Commissions",
        subtitle: "Suivez vos gains et revenus d'affiliation",
        export: "Exporter",
        total_earned: "Total gagné",
        pending: "En attente",
        pending_amount: "Montant en attente",
        paid: "Payé",
        paid_amount: "Montant payé",
        cancelled: "Annulé",
        this_month: "Ce mois",
        last_month: "Mois dernier",
        growth: "Croissance",
        filter_all: "Tous",
        filter_pending: "En attente",
        filter_paid: "Payés",
        filter_cancelled: "Annulés",
        history: "Historique des commissions",
        all: "Tous",
        no_commissions: "Aucune commission",
        no_commissions_desc: "Vous n'avez pas encore de commissions. Parrainez des utilisateurs pour commencer à gagner !",
        level: "Niveau",
        level_1: "Niveau 1",
        levels_2_10: "Niveaux 2-10",
        direct: "Direct",
        indirect: "Indirect",
        direct_referral: "Parrainage direct",
        indirect_referral: "Parrainage indirect",
        source: "Source",
        amount: "Montant",
        date: "Date",
        status: "Statut",
        affiliate_program: "Programme d'Affiliation",
        ten_levels_description: "Gagnez des commissions sur 10 niveaux de parrainage",
        no_commissions_description: "Parrainez des utilisateurs pour commencer à gagner des commissions",
        go_to_affiliates: "Voir mes affiliés",
        types: {
          AD_REVENUE: "Revenus Publicitaires",
          CLUB_MEMBERSHIP: "Abonnement Club",
          SHOP_PURCHASE: "Achat Boutique",
          CONTEST_PARTICIPATION: "Participation Concours",
          KYC_PAYMENT: "Paiement KYC",
          EFM_MEMBERSHIP: "Abonnement EFM",
          MFM_MEMBERSHIP: "FM Joining Fees",
          FOUNDING_MEMBERSHIP_FEE: "Adhésion Founding Member",
          ANNUAL_MEMBERSHIP_FEE: "Cotisation Annuelle FM",
          MONTHLY_REVENUE_POOL: "Pool Mensuel (5%)",
          ANNUAL_PROFIT_POOL: "Pool Annuel (10%)"
        },
        rates: {
          founding_direct: "20$ par parrainage direct",
          founding_indirect: "2$ par parrainage indirect (N2-10)",
          annual_direct: "10$ par parrainage direct",
          annual_indirect: "1$ par parrainage indirect (N2-10)"
        },
        direct: "Direct",
        indirect: "Indirect",
        sort_by_date: "Par date",
        sort_by_amount: "Par montant",
        sort_by_type: "Par type",
        filter_all: "Tous les types",
        filter_by_type: "Filtrer par type",
        filter_by_status: "Filtrer par statut"
      },
      subtitle: "Suivez votre progression, gérez vos concours et développez votre réseau",
      quick_actions: "Actions Rapides",
      recent_activity: "Activité Récente",
      no_activity: "Aucune activité récente",
      position: {
        title: "Ma Position",
        no_contests: "Aucun concours en cours",
        rank: "Rang",
        points: "Points",
        contests: "Concours Beauté",
        clubs: "Club Premium",
        affiliates: "Affiliés",
        status: "Statut",
        members: "Membres",
        referrals: "Référrés",
        commissions: "Commissions",
        active: "Actif"
      },
      contests: {
        title: "Concours",
        description: "Découvrez et participez aux concours les plus populaires",
        no_contests: "Aucun concours disponible",
        no_description: "Aucune description disponible",
        all: "Tout",
        nomination: "Nominations",
        participations: "Participations",
        filter_level: "Niveau",
        level_city: "Ville",
        level_country: "Pays",
        all_levels: "Tous les niveaux",
        nomination_hint: "Nominez d'autres personnes pour les faire participer aux compétitions. Votez pour les candidats nominés par leurs fans.",
        participations_hint: "Participez vous-même aux compétitions. Les candidats s'inscrivent directement pour concourir.",
        nominate: "Nommer",
        edit_nomination: "Modifier votre Nomination",
        edit_participation: "Modifier votre Participation",
        edit: "Modifier",
        tooltip_nominate: "Cliquez pour nommer à ce concours et soumettre votre candidature",
        time_remaining_to_nominate: "Temps restant pour nommer",
        search_placeholder: "Rechercher un concours...",
        search_button: "Rechercher",
        sort: "Trier par",
        sort_participants: "Plus de participants",
        sort_votes: "Plus de votes",
        sort_date: "Plus récent",
        sort_name: "Nom (A-Z)",
        voting_type: "Type de vote",
        voting_level_country: "National",
        voting_level_city: "Ville",
        voting_level_regional: "Régional",
        voting_level_continent: "Continental",
        voting_level_global: "Global",
        status: "Statut",
        level: "Niveau",
        city: "Ville",
        country: "National",
        continental: "Continental",
        regional: "Régional",
        global: "Global",
        contestants: "Participants",
        likes: "J'aime",
        comments: "Commentaires",
        received: "Reçu",
        participate: "Concourir",
        contest_type: {
          beauty: "Beauté",
          handsome: "Beau Gosse",
          latest_hits: "Derniers Hits",
          talent: "Talent",
          photography: "Photographie",
          fitness: "Fitness",
          fashion: "Mode",
          music: "Musique",
          dance: "Danse",
          cooking: "Cuisine",
          art: "Art",
          comics: "Comics",
          other: "Autre"
        },
        men: "Hommes",
        women: "Femmes",
        add_favorite: "Ajouter aux favoris",
        remove_favorite: "Retirer des favoris",
        added_to_favorites: "Ajouté aux favoris",
        removed_from_favorites: "Retiré des favoris",
        open: "Ouvert",
        open_for_candidacy: "Ouvert pour candidater",
        closed: "Fermé",
        submission_closed: "Le concours est fermé pour ce concours.",
        submission_closed_message: "La date limite de soumission est dépassée.",
        no_active_rounds: "Aucun round actif n'accepte les soumissions pour le moment.",
        requirements: "Conditions requises",
        kyc_required: "Vérification d'identité",
        kyc_required_description: "Seuls les participants avec une identité vérifiée peuvent participer à ce concours",
        visual_verification: "Photo de vous requise",
        visual_verification_description: "Une photo de vous est obligatoire pour participer à ce concours",
        voice_verification: "Vérification vocale",
        voice_verification_description: "Une vérification vocale est obligatoire pour participer à ce concours",
        brand_verification: "Marque vérifiée",
        brand_verification_description: "Seules les marques vérifiées peuvent participer à ce concours",
        content_verification: "Contenu original requis",
        content_verification_description: "Seul le contenu original est autorisé pour participer à ce concours",
        gender_restriction: "Restriction de genre",
        gender_restriction_female_description: "Seules les participantes féminines sont autorisées à participer à ce concours",
        gender_restriction_male_description: "Seuls les participants masculins sont autorisés à participer à ce concours",
        age_restriction: "Restriction d'âge",
        age_restriction_description: "Seuls les participants dans la tranche d'âge spécifiée peuvent participer",
        years: "ans",
        max_favorites: "5 favoris maximum",
        favorite_limit_reached: "Limite de 5 favoris atteinte",
        top_participants: "Top Participants",
        top_5_description: "Les 5 meilleurs participants du concours",
        view_contestants: "Voir les participants",
        view_all_contestants: "Voir tous les participants",
        top_contestants: "Top Contestants",
        time_remaining: "Temps restant",
        candidacy_ends: "Fin des candidatures",
        participation_ongoing: "Les candidatures sont encore ouvertes",
        vote: "Voter",
        view_details: "Voir les détails",
        already_voted: "Déjà voté",
        already_voted_message: "Vous avez déjà voté pour ce participant.",
        cannot_vote: "Vous ne pouvez pas voter pour ce participant",
        votes: "votes",
        submission: "Soumission",
        voting: "Vote",
        start: "Début",
        end: "Fin",
        add_to_favorites: "Ajouter aux favoris",
        remove_from_favorites: "Retirer des favoris",
        share: "Partager",
        share_title: "Partager ce participant",
        share_description: "Partagez ce participant avec vos amis et votre réseau",
        share_link_label: "Lien de partage",
        copy: "Copier",
        copied: "Copié",
        share_natively: "Partager nativement",
        report: "Signaler",
        reactions: "Réactions",
        you_reacted: "Vous avez réagi",
        no_reactions: "Aucune réaction pour le moment",
        people_reacted: "personnes ont réagi",
        be_first_to_react: "Soyez le premier à réagir",
        participant: "Participant",
        rank: "Classement",
        reaction: "Réaction",
        search_contestant: "Rechercher un participant...",
        filtered_by_country: "Filtré par votre pays",
        no_contestants: "Aucun participant pour le moment",
        no_contestants_found: "Aucun participant trouvé",
        like: "J'aime",
        love: "J'adore",
        wow: "Wow",
        dislike: "Je n'aime pas",
        favorite: "Favori",
        comments_description: "Partagez vos pensées sur ce participant",
        add_comment_placeholder: "Ajouter un commentaire...",
        sending: "Envoi...",
        send: "Envoyer",
        no_comments: "Aucun commentaire pour le moment",
        cancel: "Annuler",
        mention_hint: "Tapez @ pour mentionner quelqu'un",
        edit: "Modifier",
        delete: "Supprimer",
        vote_error: "Erreur lors du vote. Veuillez réessayer.",
        voting_not_open: "Le vote n'est pas encore ouvert pour ce concours.",
        already_voted_error: "Déjà voté.",
        cannot_vote_own: "Vous ne pouvez pas voter pour votre propre candidature.",
        vote_success: "Vote enregistré avec succès!",
        vote_gender_restriction_male: "Ce concours est réservé aux participants masculins. Seules les participantes féminines peuvent voter.",
        vote_gender_restriction_female: "Ce concours est réservé aux participantes féminines. Seuls les participants masculins peuvent voter.",
        vote_gender_not_set: "Votre profil ne contient pas d'information de genre. Veuillez compléter votre profil pour voter dans ce concours.",
        my_applications: {
          title: "Mes Candidatures",
          description: "Consultez vos candidatures et votre classement",
          no_applications: "Vous n'avez pas encore de candidatures",
          browse_contests: "Parcourir les concours",
          status: "Statut",
          status_pending: "En attente",
          status_approved: "Approuvée",
          status_rejected: "Rejetée",
          rank: "Rang",
          view_details: "Voir les détails",
          view_page: "Voir la page",
          edit_not_available: "Édition non disponible pour ce contest",
          delete_not_available: "Suppression non disponible pour ce contest",
          delete_confirm_message: "Êtes-vous sûr de vouloir supprimer cette candidature ? Cette action ne peut pas être annulée.",
          details: "Détails",
          statistics: "Statistiques",
          total_shares: "Total de partages",
          shares_by_platform: "Partages par plateforme",
          no_shares: "Aucun partage pour le moment",
          contest: "Concours",
          date: "Date",
          media: "Médias",
          no_title: "Sans titre",
          user: "Utilisateur",
          media_alt: "Média",
          video_alt: "Vidéo",
          report: "Signaler",
          already_reported: "Déjà signalé"
        },
        suggest_contest: {
          title: "Suggérer un concours",
          description: "Proposez une idée de concours à notre équipe",
          button: "Suggérer un concours",
          name_label: "Nom du concours",
          name_placeholder: "Ex: Concours de beauté 2024",
          description_label: "Description",
          description_placeholder: "Décrivez votre idée de concours...",
          category_label: "Catégorie",
          category_placeholder: "Sélectionnez une catégorie",
          submit: "Envoyer la suggestion",
          submitting: "Envoi en cours...",
          success: "Votre suggestion a été envoyée avec succès !",
          success_message: "Merci pour votre suggestion. Notre équipe l'examinera et vous tiendra informé.",
          cancel: "Annuler",
          error: {
            name_required: "Le nom du concours est requis",
            category_required: "La catégorie est requise",
            submit_error: "Erreur lors de l'envoi de la suggestion",
            network_error: "Erreur de connexion. Vérifiez votre connexion internet.",
            server_error: "Erreur serveur. Veuillez réessayer plus tard."
          }
        },
        report_contestant: {
          title: "Signaler un participant",
          description: "Décrivez la raison de votre signalement. Notre équipe examinera votre demande.",
          contestant: "Participant",
          reason_label: "Raison du signalement",
          reason_placeholder: "Sélectionnez une raison",
          description_label: "Description détaillée",
          description_placeholder: "Décrivez en détail la raison de votre signalement (minimum 10 caractères)...",
          characters: "caractères",
          submit: "Envoyer le signalement",
          submitting: "Envoi en cours...",
          success: "Votre signalement a été envoyé avec succès !",
          cancel: "Annuler",
          reasons: {
            spam: "Spam",
            inappropriate: "Contenu inapproprié",
            harassment: "Harcèlement",
            fake: "Faux compte",
            copyright: "Violation de droits d'auteur",
            other: "Autre"
          },
          error: {
            reason_required: "La raison est requise",
            description_required: "La description est requise",
            description_min_length: "La description doit contenir au moins 10 caractères",
            submit_error: "Erreur lors de l'envoi du signalement",
            network_error: "Erreur de connexion. Vérifiez votre connexion internet.",
            server_error: "Erreur serveur. Veuillez réessayer plus tard."
          }
        },
        participation_form: {
          title: "Participer au concours",
          description: "Sélectionnez votre meilleure photo ou vidéo pour participer à ce concours",
          edit_title: "Modifier un Candidat",
          edit_description: "Mettez à jour les détails de votre soumission",
          nominate_title: "Nommer un Candidat",
          nominate_description: "Importez votre vidéo depuis YouTube ou TikTok",
          select_media: "Sélectionner votre média",
          drag_drop: "Glissez-déposez votre fichier ici",
          file_info: "ou cliquez pour sélectionner (Images: JPG, PNG, GIF | Vidéos: MP4, WebM | Max: 100MB)",
          submit: "Soumettre ma candidature",
          success: "Votre candidature a été soumise avec succès. Elle sera examinée par notre équipe.",
          success_title: "✅ Candidature soumise avec succès !",
          success_edit: "Votre candidature a été mise à jour avec succès.",
          already_participating: "ℹ️ Vous avez déjà une candidature pour ce concours. Vous ne pouvez soumettre qu'une seule candidature par concours.",
          edit_participation: "Modifier ma candidature",
          click_add_images: "Cliquez pour ajouter des images",
          preparing: "Préparation...",
          checking_files: "Vérification des fichiers...",
          uploading: "Upload en cours...",
          images_format: "Images",
          click_add_video: "Cliquez pour ajouter une vidéo",
          video_format: "Vidéo",
          cancel: "Annuler",
          error: {
            no_media_selected: "Veuillez sélectionner un fichier",
            invalid_file_type: "Type de fichier non supporté",
            file_too_large: "Le fichier est trop volumineux (max 100MB)",
            contest_not_found: "Concours non trouvé",
            submit_error: "Erreur lors de la soumission",
            gender_restriction_male: "Ce concours est réservé aux participants masculins uniquement.",
            gender_restriction_female: "Ce concours est réservé aux participantes féminines uniquement.",
            gender_not_set: "Votre profil ne contient pas d'information de genre. Veuillez compléter votre profil pour participer à ce concours.",
            already_submitted: "Vous avez déjà soumis une candidature pour ce concours.",
            submission_closed: "Les inscriptions sont fermées pour ce concours.",
            deadline_passed: "La date limite de soumission est dépassée."
          }
        }
      },
      favorites: {
        title: "Mes Favoris",
        description: "Consultez vos contests et candidats favoris",
        description_contestants: "Organisez vos contestants favoris par glisser-déposer",
        contests_tab: "Concours",
        contestants_tab: "Candidats",
        no_favorite_contests: "Vous n'avez pas encore de concours favoris",
        no_favorite_contestants: "Vous n'avez pas encore de candidats favoris",
        no_favorites_yet: "Aucun favori pour le moment",
        no_favorites_hint: "Ajoutez des contestants à vos favoris depuis la page d'un concours en cliquant sur l'étoile.",
        browse_contests: "Parcourir les concours"
      },
      myhigh5: {
        title: "MyHigh5",
        description: "Les 5 contestants pour lesquels vous avez voté",
        hint: "Votre premier vote est affiché en position 1, et votre vote le plus récent en position 5. Vous pouvez voter pour un maximum de 5 contestants.",
        no_votes: "Aucun vote",
        no_votes_description: "Vous n'avez pas encore voté pour des contestants. Explorez les concours pour voter!",
        explore_contests: "Explorer les concours",
        explore_more: "Explorer plus de concours",
        remaining_votes: "Vous pouvez encore voter pour {count} contestant(s)",
        votes_label: "votes",
        hint_dnd: "Glissez-déposez pour réorganiser vos votes. Le 1er reçoit 5 points, le 2ème 4 points, le 3ème 3 points, le 4ème 2 points et le 5ème 1 point. Les votes sont limités à 5 par season.",
        rank: "Rang",
        points: "Points",
        contestant: "Contestant",
        location: "Localisation",
        total_votes: "Votes totaux",
        vote_date: "Date du vote",
        order_saved: "Ordre sauvegardé !",
        order_error: "Erreur lors de la sauvegarde",
        points_legend: "Système de points",
        points_label: "points"
      }
    },
    kyc: {
      verification_required: "Vérification d'identité requise",
      verification_required_description: "Pour participer aux concours et retirer vos gains, vous devez vérifier votre identité.",
      start_verification: "Démarrer la vérification",
      already_verified: "Identité vérifiée",
      already_verified_description: "Votre identité a été vérifiée avec succès. Vous pouvez maintenant profiter de toutes les fonctionnalités.",
      verification_in_progress: "Vérification en cours",
      verification_in_progress_description: "Votre demande de vérification est en cours de traitement. Nous vous notifierons dès que le processus sera terminé.",
      verification_continue_description: "Vous avez une vérification en cours. Vous pouvez la continuer ou actualiser le statut.",
      continue_verification: "Continuer la vérification",
      login_required: "Veuillez vous connecter pour continuer",
      init_error: "Impossible de démarrer la vérification",
      max_attempts_reached: "Nombre maximum de tentatives atteint",
      max_attempts_description: "Vous avez utilisé toutes vos tentatives de vérification. Veuillez contacter notre support pour obtenir de l'aide.",
      max_attempts_can_pay: "Vous avez utilisé vos tentatives gratuites. Vous pouvez acheter des tentatives supplémentaires pour continuer.",
      buy_attempts: "Acheter des tentatives supplémentaires",
      price_per_attempt: "Prix par tentative",
      pay_and_retry: "Payer et réessayer",
      attempts_remaining: "Tentatives restantes",
      attempts_used: "Tentatives utilisées",
      verification_status: "Statut de vérification",
      verification_status_description: "Consultez le statut de votre vérification d'identité",
      verification_rejected: "Vérification refusée",
      verification_rejected_description: "Votre demande de vérification a été refusée. Vous pouvez soumettre une nouvelle demande.",
      rejection_reason: "Raison du refus",
      submitted_on: "Soumis le",
      submit_again: "Réessayer",
      verification_steps: "Comment ça marche ?",
      step_1_title: "1. Informations personnelles",
      step_1_desc: "Renseignez vos informations personnelles de base",
      step_2_title: "2. Document d'identité",
      step_2_desc: "Prenez en photo votre pièce d'identité",
      step_3_title: "3. Selfie de vérification",
      step_3_desc: "Prenez un selfie pour confirmer votre identité",
      accepted_documents: "Documents acceptés",
      doc_passport: "Passeport",
      doc_id_card: "Carte d'identité",
      doc_driving_license: "Permis de conduire",
      initiating: "Démarrage...",
      redirect_notice: "Vous serez redirigé vers notre partenaire de vérification sécurisé",
      follow_instructions: "Suivez les instructions ci-dessous pour compléter votre vérification d'identité.",
      secure_verification: "Vérification sécurisée par notre partenaire certifié",
      uploaded_documents: "Documents téléchargés",
      document_front: "Avant du document",
      document_back: "Arrière du document",
      selfie: "Selfie",
      steps: "Étapes de vérification",
      personal_info: "Informations personnelles",
      personal_info_desc: "Entrez vos informations personnelles",
      document_info: "Informations du document",
      document_info_desc: "Fournissez les détails de votre document",
      review_submit: "Vérifier et soumettre",
      review_submit_desc: "Vérifiez et soumettez vos informations",
      secure: "Vos données sont sécurisées",
      secure_desc: "Toutes vos informations sont chiffrées et protégées selon les normes internationales.",
      first_name: "Prénom",
      first_name_placeholder: "Entrez votre prénom",
      last_name: "Nom de famille",
      last_name_placeholder: "Entrez votre nom de famille",
      date_of_birth: "Date de naissance",
      nationality: "Nationalité",
      nationality_placeholder: "Entrez votre nationalité",
      address: "Adresse",
      address_placeholder: "Entrez votre adresse complète",
      document_type: "Type de document",
      passport: "Passeport",
      national_id: "Carte d'identité",
      drivers_license: "Permis de conduire",
      document_number: "Numéro du document",
      document_number_placeholder: "Entrez votre numéro de document",
      issuing_country: "Pays d'émission",
      issuing_country_placeholder: "Entrez le pays qui a émis votre document",
      document_upload_next: "Téléchargement de document à venir",
      document_upload_next_desc: "À l'étape suivante, vous téléchargerez des photos de votre document (avant et arrière) et un selfie.",
      processing_time: "Délai de traitement",
      processing_time_desc: "Votre vérification sera traitée dans les 24 à 48 heures. Vous recevrez une notification par email une fois terminée.",
      submission_success: "Vérification soumise avec succès! Redirection en cours...",
      submit_verification: "Soumettre la vérification",
      errors: {
        first_name_required: "Le prénom est requis",
        last_name_required: "Le nom de famille est requis",
        date_of_birth_required: "La date de naissance est requise",
        nationality_required: "La nationalité est requise",
        address_required: "L'adresse est requise",
        document_type_required: "Le type de document est requis",
        document_number_required: "Le numéro de document est requis",
        issuing_country_required: "Le pays d'émission est requis",
        document_front_required: "La photo avant du document est requise",
        document_back_required: "La photo arrière du document est requise",
        selfie_required: "Le selfie est requis"
      }
    },
    payment: {
      payment_required: "Paiement requis",
      payment_instructions: "Instructions de paiement",
      payment_description: "Pour accéder à {product}, veuillez effectuer un paiement de {amount}.",
      send_exact_amount: "Envoyez exactement {amount} à l'adresse ci-dessous.",
      kyc_verification: "Vérification KYC",
      efm_membership: "Adhésion EFM",
      kyc_description: "Vérification d'identité pour participer aux concours",
      efm_description: "Devenez membre fondateur EFM",
      validity_one_year: "Validité: 1 an par unité",
      unit: "unité",
      quantity: "Quantité",
      total: "Total",
      choose_method: "Choisissez votre méthode de paiement",
      choose_product: "Choisir un produit",
      choose_product_description: "Sélectionnez le produit que vous souhaitez acheter.",
      payment_method: "Méthode de paiement",
      cryptocurrencies: "Crypto-monnaies",
      other_methods: "Autres méthodes",
      card: "Carte bancaire",
      bank_transfer: "Virement bancaire",
      network: "Réseau",
      amount_to_send: "Montant à envoyer",
      receiving_address: "Adresse de réception",
      bank_details: "Coordonnées bancaires",
      beneficiary: "Bénéficiaire",
      bank_reference_info: "Indiquez votre email en référence du virement pour faciliter l'identification.",
      network_warning: "Assurez-vous d'envoyer le montant exact sur le bon réseau. Les erreurs de réseau peuvent entraîner une perte de fonds.",
      payment_done: "J'ai effectué le paiement",
      validation_time_info: "Après votre paiement, la validation peut prendre quelques minutes à quelques heures selon la méthode choisie.",
      min: "Min",
      min_amount: "Montant minimum",
      min_amount_error: "Le montant minimum est de {amount}",
      enter_amount: "Entrez le montant",
      custom_amount: "Montant personnalisé",
      card_coming_soon: "Paiement par carte bientôt disponible",
      creating_payment: "Création du paiement...",
      order_id: "Référence",
      add_recipients: "Ajouter des bénéficiaires",
      recipients_description: "Ajoutez les utilisateurs pour lesquels vous souhaitez payer",
      method_description: "Choisissez votre méthode de paiement",
      instructions_description: "Envoyez le montant exact à l'adresse indiquée",
      recipient: "Bénéficiaire",
      username_or_email: "Nom d'utilisateur ou email",
      user_not_found: "Utilisateur non trouvé",
      product_type: "Type de produit",
      amount: "Montant",
      min_100: "Minimum 100 USD",
      add_recipient: "Ajouter un bénéficiaire",
      recipients_count: "bénéficiaire(s)",
      confirm_close_title: "Fermer le paiement ?",
      confirm_close_description: "Votre progression sera perdue. Êtes-vous sûr de vouloir fermer ?",
      pay_for_myself: "Payer pour moi",
      pay_for_others: "Payer pour d'autres",
      add_other_user: "Ajouter un autre utilisateur",
      checking: "Vérification...",
      waiting_confirmation: "Paiement en attente de confirmation...",
      not_received: "Paiement non encore reçu. Veuillez réessayer.",
      success_title: "Paiement confirmé !",
      success_description: "Votre paiement a été reçu et confirmé. Vous pouvez maintenant continuer.",
      amount_paid: "Montant payé",
      auto_checking: "Vérification automatique active",
      last_check: "Dernière vérif.",
      waiting_payment: "En attente de paiement...",
      confirming: "Paiement détecté, confirmation en cours...",
      partially_paid: "Paiement partiel reçu. Veuillez compléter le montant.",
      kyc_verification: "Service KYC",
      mfm_membership: "MFM",
      annual_membership: "Cotisation Annuelle",
      buy_services: "Acheter des services",
      select_for_myself: "Pour moi-même",
      select_service: "Sélectionnez un service pour vous",
      kyc_description: "Vérification d'identité pour participer aux concours",
      mfm_description: "Accès au pool de revenus mensuels (5%) et annuels (10%) + referrals aléatoires",
      annual_description: "Renouvellement annuel du statut Founding Member",
      total_to_pay: "Total à payer",
      card: "Carte bancaire",
      bank_transfer: "Virement bancaire",
      no_payment_id: "Aucun identifiant de paiement",
      payment_expired: "Ce paiement a expiré. Veuillez créer un nouveau paiement.",
      fetch_error: "Erreur lors du chargement des détails du paiement"
    },
    contests: {
      profile_incomplete_title: "Profil incomplet",
      profile_incomplete_message: "Complétez votre profil pour pouvoir participer aux concours.",
      complete_profile: "Compléter",
      kyc_required_title: "Vérification d'identité requise",
      kyc_required_message: "Vérifiez votre identité (KYC) pour pouvoir participer aux concours.",
      kyc_recommended_title: "Vérification d'identité recommandée",
      kyc_recommended_message: "Certains concours exigent la vérification KYC pour participer.",
      verify_identity: "Vérifier"
    },
    user: {
      profile: "Profil",
      settings: "Paramètres",
      kyc: "Vérification KYC",
      subscription: "Abonnement",
      logout: "Déconnexion"
    },
    notifications: {
      title: "Notifications",
      no_notifications: "Aucune notification",
      mark_all_read: "Tout marquer comme lu",
      mark_as_read: "Marquer comme lu",
      view_all: "Voir toutes les notifications",
      types: {
        system: "Système",
        contest: "Concours",
        compte: "Compte"
      },
      messages: {
        new_vote: "a voté pour votre candidature",
        new_comment: "a commenté votre candidature",
        new_reply: "a répondu à votre commentaire",
        new_like: "a aimé votre commentaire",
        new_reaction: "a réagi à votre candidature"
      },
      time: {
        just_now: "À l'instant",
        seconds_ago: "il y a quelques secondes",
        minute_ago: "il y a une minute",
        minutes_ago: "il y a {count} minutes",
        hour_ago: "il y a une heure",
        hours_ago: "il y a {count} heures",
        day_ago: "il y a un jour",
        days_ago: "il y a {count} jours",
        week_ago: "il y a une semaine",
        weeks_ago: "il y a {count} semaines",
        month_ago: "il y a un mois",
        months_ago: "il y a {count} mois",
        year_ago: "il y a un an",
        years_ago: "il y a {count} ans"
      }
    },
    pages: {
      contests: {
        badge: "Concours en cours",
        title: "Découvrez nos Concours",
        subtitle: "Participez, nommez ou votez dans des compétitions passionnantes qui progressent du niveau local au niveau mondial.",
        search_placeholder: "Rechercher un concours...",
        filters: {
          all: "Tous",
          city: "Ville",
          country: "Pays",
          regional: "Régional",
          continental: "Continental",
          global: "Global"
        },
        stats: {
          active: "Concours actifs",
          participants: "Participants",
          levels: "Niveaux"
        },
        all_contests: "Tous les concours",
        contests_filter: "Concours",
        results: "résultat",
        reset_filters: "Réinitialiser les filtres",
        join_community: "Rejoignez la communauté",
        learn_more: "En savoir plus",
        no_results: "Aucun concours trouvé",
        try_different_filter: "Essayez un autre filtre ou terme de recherche",
        auth_required_title: "Connexion requise",
        auth_required_description: "Vous devez être connecté pour participer aux concours ou voir les participants.",
        auth_required_benefits_title: "En vous connectant, vous pourrez :",
        auth_required_benefit_participate: "Participer aux concours",
        auth_required_benefit_view_contestants: "Voir les participants",
        auth_required_benefit_vote: "Voter pour vos favoris",
        auth_required_benefit_comment: "Commenter et interagir",
        auth_required_login: "Se connecter",
        auth_required_register: "Créer un compte",
        cta: {
          title: "Prêt à participer ?",
          subtitle: "Créez votre compte gratuitement et commencez à participer aux concours dès aujourd'hui !",
          button: "Créer mon compte"
        }
      },
      clubs: {
        title: "Fan Clubs Exclusifs",
        subtitle: "Rejoignez des communautés passionnées et accédez à du contenu exclusif",
        search_placeholder: "Rechercher un club...",
        features: {
          dsp: "Paiement DSP",
          multi_admin: "Multi-Admin",
          affiliate: "Programme Affilié"
        },
        no_results: "Aucun club trouvé",
        try_different_filter: "Essayez un autre filtre",
        cta: {
          title: "Créez votre propre Club",
          subtitle: "Monétisez votre contenu, gérez votre communauté et gagnez grâce au programme d'affiliation.",
          feature1: "Paiements sécurisés via DSP",
          feature2: "Gestion multi-administrateurs",
          feature3: "10% de commission sur les ventes",
          button: "Créer mon Club"
        }
      },
      about: {
        title: "À Propos de MyHigh5",
        subtitle: "La première plateforme holistique de concours en ligne qui découvre et met en valeur les talents du niveau local à la scène mondiale.",
        mission: {
          title: "Notre Mission",
          description: "Démocratiser l'accès aux concours et permettre à chaque talent de briller sur la scène mondiale."
        },
        values: {
          title: "Nos Valeurs",
          subtitle: "Les principes qui guident chacune de nos décisions"
        },
        timeline: {
          title: "Notre Parcours"
        },
        team: {
          title: "Notre Équipe",
          subtitle: "Des passionnés dédiés à votre succès"
        },
        cta: {
          title: "Rejoignez l'Aventure MyHigh5",
          subtitle: "Faites partie d'une communauté mondiale de talents.",
          button: "Commencer Maintenant"
        }
      },
      contact: {
        title: "Contactez-nous",
        subtitle: "Notre équipe est là pour vous aider. Nous répondons généralement sous 24h.",
        form: {
          title: "Envoyez-nous un message",
          name: "Nom complet",
          email: "Email",
          category: "Catégorie",
          subject: "Sujet",
          message: "Message",
          submit: "Envoyer le message"
        },
        faq: {
          title: "Questions Fréquentes"
        },
        hours: {
          title: "Heures de support"
        },
        categories: {
          title: "Comment pouvons-nous vous aider ?"
        }
      }
    },
    verification: {
      requirements_title: "Vérifications requises",
      requirements_description: "Ce concours nécessite les vérifications suivantes pour participer.",
      contest: "Concours",
      progress: "Progression",
      completed: "Complété",
      required: "Requis",
      verify: "Vérifier",
      proceed: "Continuer",
      incomplete_warning: "Complétez toutes les vérifications pour pouvoir participer.",
      kyc_verification: "Vérification KYC",
      visual_verification: "Vérification visuelle (Selfie)",
      voice_verification: "Vérification vocale",
      selfie: "Selfie de vérification",
      selfie_with_pet: "Selfie avec votre animal",
      selfie_with_document: "Selfie avec document",
      selfie_instructions: "Prenez une photo claire de votre visage, bien éclairé.",
      selfie_pet_instructions: "Prenez une photo claire de vous avec votre animal de compagnie.",
      selfie_document_instructions: "Prenez une photo de vous avec une pièce d'identité visible.",
      voice_instructions: "Enregistrez votre voix pendant quelques secondes.",
      use_camera: "Utiliser la caméra",
      upload_image: "Importer une image",
      camera_error: "Impossible d'accéder à la caméra",
      microphone_error: "Impossible d'accéder au microphone",
      file_too_large: "Le fichier est trop volumineux",
      file_too_large_with_size: "Le fichier est trop volumineux. Taille maximale autorisée",
      invalid_file_type: "Type de fichier invalide",
      upload_error: "Erreur lors de l'envoi",
      capture: "Capturer",
      retake: "Reprendre",
      confirm: "Confirmer",
      tap_to_record: "Appuyez pour enregistrer",
      recording: "Enregistrement en cours...",
      recording_complete: "Enregistrement terminé",
      play: "Écouter",
      stop: "Stop",
      selfie_success: "Selfie enregistré avec succès",
      voice_success: "Enregistrement vocal enregistré avec succès"
    }
  },
  en: {
    not_found: {
      title: "Page Not Found",
      description: "Sorry, the page you are looking for does not exist or has been moved.",
      go_back: "Go Back",
      go_home: "Home",
      quick_links: "Quick Links",
      help_text: "If you think this is an error, please contact our support."
    },
    common: {
      loading: "Loading...",
      error: "An error occurred",
      success: "Success",
      cancel: "Cancel",
      confirm: "Confirm",
      continue: "Continue",
      or: "or",
      redirecting: "Redirecting...",
      please_wait: "Please wait...",
      back: "Back",
      back_to_dashboard: "Back to dashboard",
      previous: "Previous",
      next: "Next",
      submitting: "Submitting...",
      no_documents: "No documents",
      profile_setup: "Profile Setup",
      profile_setup_description: "Complete your profile to continue",
      edit: "Edit",
      delete: "Delete",
      deleting: "Deleting...",
      confirm_delete: "Confirm delete",
      deleted_successfully: "Deleted successfully",
      likes: "Likes",
      comments: "Comments",
      search: "Search",
      clear: "Clear",
      welcome: "Welcome",
      access_denied: "Access denied",
      no_permission: "You do not have permission to perform this action",
      refresh: "Refresh",
      network_error: "Network error",
      optional: "(optional)",
      save: "Save",
      unknown: "Unknown",
      load_more: "Load more",
      actions: "Actions"
    },
    admin: {
      title: "Administration Panel",
      subtitle: "Manage your platform",
      nav: {
        main: "Main",
        dashboard: "Dashboard",
        management: "Management",
        seasons: "Seasons",
        contests: "Contests",
        contestants: "Contestants",
        users: "Users",
        kyc: "KYC",
        reports: "Reports",
        configuration: "Configuration",
        categories: "Categories",
        commission_settings: "Commission Settings",
        suggested_contests: "Suggested Contests",
        transactions: "Transactions",
        microservices: "Microservices",
        accounting: "Accounting"
      },
      dashboard: {
        total_seasons: "Total seasons",
        active: "active",
        inactive: "inactive",
        admins: "admins",
        votes: "Votes",
        total_votes: "Total votes",
        comments: "Comments",
        total_comments: "Total comments",
        quick_actions: "Quick actions",
        user_progress: "User Progress",
        reports: {
          title: "Reports",
          description: "Generate and view your reports",
          financial_report: "Financial Report",
          financial_description: "Revenue, expenses and profits",
          users_report: "Users Report",
          users_description: "Statistics and progression",
          contests_report: "Contests Report",
          contests_description: "Contest performance",
          votes_report: "Votes Report",
          votes_description: "Vote analysis",
          recent_reports: "Recent Reports"
        },
        chart_labels: {
          total_users: "Total users",
          active_users: "Active users",
          new_users: "New users"
        },
        periods: {
          today: "Today",
          yesterday: "Yesterday",
          week: "Week",
          month: "Month",
          year: "Year"
        },
        statistics: {
          total_deposits: "Total Deposits",
          total_withdrawals: "Total Withdrawals",
          verified_users: "Verified Users",
          reports: "Reports",
          categories: "Categories",
          deposits_chart: "Deposits Chart",
          withdrawals_chart: "Withdrawals Chart",
          categories_chart: "Categories Statistics",
          reports_by_type: "Reports by Type",
          amount_eur: "Amount ($)",
          deposits_count: "deposits",
          withdrawals_count: "withdrawals",
          kyc_verified: "KYC verified",
          reports_count: "Reports",
          categories_total: "Total",
          amount: "Amount",
          count: "Count",
          contests: "Contests",
          uses: "Uses",
          period: "Period:",
          custom: "Custom",
          apply: "Apply",
          loading: "Loading...",
          refresh: "Refresh",
          no_data_available: "No data available"
        }
      },
      profile: {
        participations: "Participations",
        total_votes: "Votes",
        total_favorites: "Favorites",
        followers: "Followers",
        following: "Following",
        contestants: "Entries",
        all_rounds: "All",
        no_entries: "No entries yet",
        verified: "Verified",
        years: "years old",
        follow: "Follow",
        unfollow: "Unfollow",
        followed: "You are now following this user",
        unfollowed: "You unfollowed this user"
      },
      rounds: {
        title: "Manage Rounds",
        description: "Manage contest rounds",
        new_round: "New Round",
        edit: "Edit Round",
        create: "Create Round",
        contest: "Contest",
        select_contest: "Select a contest",
        name: "Round Name",
        status: "Status",
        load_error: "Error loading rounds",
        delete_success: "Round deleted successfully",
        delete_error: "Error deleting round",
        update_success: "Round updated successfully",
        create_success: "Round created successfully",
        search: "Search rounds...",
        confirm_delete: "Delete round",

        delete_warning: "Are you sure you want to delete this round?",
        city_season: "City Season",
        country_season: "Country Season",
        regional_season: "Regional Season",
        continental_season: "Continental Season",
        global_season: "Global Season",
        start_date: "Start Date",
        end_date: "End Date"
      },
      seasons: {
        title: "Manage Seasons",
        description: "Create, edit and manage contest seasons",
        new_season: "New Season",
        edit_season: "Edit Season",
        create_season: "Create Season",
        year: "Year",
        season_number: "Season Number",
        season_title: "Title",
        status: "Status",
        start_date: "Start Date",
        end_date: "End Date",
        upload_end_date: "Upload End",
        upcoming: "Upcoming",
        upload_phase: "Upload Phase",
        voting_active: "Voting Active",
        voting_ended: "Voting Ended",
        completed: "Completed",
        cancelled: "Cancelled",
        edit: "Edit",
        delete: "Delete",
        cancel: "Cancel",
        create: "Create",
        confirm_delete: "Are you sure you want to delete this season?",
        confirm_delete_title: "Delete Season",
        confirm_delete_message: "Are you sure you want to delete this season? This action is irreversible.",
        no_seasons: "No seasons found. Create your first season.",
        create_success: "Season created successfully",
        update_success: "Season updated successfully",
        delete_success: "Season deleted successfully",
        load_error: "Error loading seasons",
        save_error: "Error saving",
        delete_error: "Error deleting",
        level: "Level",
        level_city: "City",
        level_country: "Country",
          filter_level: "Level",
        level_regional: "Regional",
        level_continent: "Continent",
        level_global: "Global",
        level_placeholder: "Select a level",
        season_title_placeholder: "Ex: Spring 2024 Season",
        error_level_exists: "A season with the level '{level}' already exists. There can only be one active season per level.",
        error_invalid_level: "Invalid level. Valid levels are: {levels}",
        contestants_count: "contestants",
        contests_count: "contests"
      },
      contests: {
        title: "Manage Contests",
        tab_contests: "Contests",
        tab_rounds: "Rounds",
        description: "Create, edit and manage contests",
        new_contest: "New Contest",
        edit_contest: "Edit Contest",

        create_contest: "Create Contest",
        name: "Contest Name",
        contest_description: "Contest description",
        contest_type: "Contest Type",
        level: "Level",
        city: "City",
        country: "Country",
        region: "Region",
        continent: "Continent",
        global: "Global",
        active: "Active",
        inactive: "Inactive",
        upload_open: "Upload Open",
        voting_active: "Voting Active",
        edit: "Edit",
        delete: "Delete",
        cancel: "Cancel",
        confirm_delete: "Are you sure you want to delete this contest?",
        image: "Contest Image",
        no_contests: "No contests found",
        voting_restriction: "Who can Contest",
        none: "None",
        male_only: "Male Only",
        female_only: "Female Only",
        geographic: "Geographic",
        age_restricted: "Age Restricted",
        start_date: "Start Date",
        end_date: "End Date",
        search_placeholder: "Search contests...",
        sort: "Sort by",
        season: "Season",
        select_season: "Select a season",
        delete_warning: "This action is irreversible. Are you sure you want to delete this contest?",
        create_success: "Contest created successfully",
        create_error: "Error creating contest",
        update_success: "Contest updated successfully",
        update_error: "Error updating contest",
        delete_success: "Contest deleted successfully",
        delete_error: "Error deleting contest",
        sort_date: "Date (Recent)",
        sort_name: "Name (A-Z)",
        sort_status: "Status",
        participant_count: "Limit of Contestants",
        all_loaded: "All contests displayed",
        creating: "Creating...",
        updating: "Updating...",
        candidates: "Candidates",
        confirm_delete_title: "Delete Contest",
        confirm_delete_message: "Are you sure you want to delete this contest? This action is irreversible.",
        submission_start: "Submission Start",
        submission_end: "Submission End",
        voting_start: "Voting Start",
        voting_end: "Voting End",
        contest_dates: "Contest Dates",
        approved: "Approved",
        rejected: "Rejected",
        filter: "Filter",
        approve: "Approve",
        reject: "Reject",
        view: "View",
        no_kyc: "No KYC verification",
        verification_score: "Confidence Score",
        identity: "Identity",
        document: "Document",
        address: "Address",
        face: "Face",
        confidence_score: "Score",
        rejection_reason: "Rejection Reason",
        // Verification form labels
        participant_type: "Participant type",
        verification_type: "Verification type",
        min_age: "Minimum age",
        max_age: "Maximum age",
        requires_kyc: "KYC required",
        requires_visual: "Visual verif.",
        requires_voice: "Voice verif.",
        requires_brand: "Brand verif.",
        requires_content: "Content ownership verif.",
        // List stats
        participants: "Participants",
        pending: "Pending",
        // Media requirements
        media_requirements: "Media Requirements",
        requires_video: "Video required",
        max_videos: "Max videos",
        video_duration: "Max duration (min)",
        min_images: "Min images",
        max_images: "Max images",
        // List translations
        level_city: "City",
        level_country: "Country",
          filter_level: "Level",
        level_region: "Region",
        level_continent: "Continent",
        level_global: "Global",
        contests_count: "contests",
        active_count: "active",
        result: "result",
        results: "results",
        found: "found",
        no_results_for: "No results for",
        current_image: "Current image",
        participant_individual: "Individual",
        participant_pet: "Pet",
        participant_club: "Club",
        participant_content: "Content",
        kyc_required: "KYC required",
        kyc_not_required: "No KYC",
        verification_visual: "Visual",
        verification_voice: "Voice",
        verification_brand: "Brand",
        verification_content: "Content",
        age_restricted: "Age restricted",
        years: "years",
        // Form placeholders
        name_placeholder: "Ex: Beauty Contest 2024",
        description_placeholder: "Contest description",
        type_placeholder: "Ex: beauty, handsome",
        // Auto dates
        auto_dates_title: "Automatic dates",
        auto_dates_description: "Dates are automatically generated",
        auto_date_upload_start: "Upload start: creation date",
        auto_date_upload_end: "Upload end: 1 month after start",
        auto_date_vote_start: "Voting start: 1 day after upload end",
        auto_date_vote_end: "Voting end: 1 month after voting start",
        // Additional form labels
        verification_requirements: "Verification requirements",
        verification_none: "None",
        none: "None",
        male_only: "Men only",
        female_only: "Women only",
        geographic: "Geographic",
        // Additional placeholders
        min_age_placeholder: "Ex: 18",
        max_age_placeholder: "Ex: 35",
        search_input_placeholder: "Name, type, description...",
        sort: "Sort by",
        // Season dates
        season_dates: "Season Dates",
        season_dates_description_edit: "These dates are automatically calculated from the voting start date. You can modify them manually if necessary.",
        season_dates_description_create: "These dates will be automatically calculated from the voting start date when creating. You can pre-fill them if necessary.",
        city_season: "City Season",
        country_season: "Country Season",
        regional_season: "Regional Season",
        continental_season: "Continental Season",
        global_season: "Global Season",
        start_date: "Start Date",
        end_date: "End Date",
        // Voting type translations
        voting_type: "Contesting Type",
        select_voting_type: "Select a contesting type",
        new_voting_type: "New voting type",
        voting_types_load_error: "Error loading voting types",
        voting_type_created: "Voting type created successfully",
        voting_type_create_error: "Error creating voting type",
        create_voting_type: "Create a voting type",
        voting_type_name_placeholder: "Ex: City Vote - Advert Commission",
        voting_level: "Voting level",
        commission_source: "Commission source",
        commission_rules: "Commission rules (JSON)",
        commission_rules_help: "Commission rules are optional. Format: L1 for level 1, L2-10 for levels 2 to 10.",
        commission_advert: "Advertisement",
        commission_affiliate: "Affiliate",
        commission_kyc: "KYC",
        commission_mfm: "MFM",
        create: "Create",
        // Dialog titles
        create_nomination_contest: "Create a new (Nomination Contest)",
        create_participation_contest: "Create a new (Participation Contest)",
        // Error messages
        error_name_required: "Contest name is required",
        error_category_required: "Category is required",
        error_description_required: "Description is required",
        error_image_required: "Contest image is required",
        error_contest_type_required: "Contesting type is required for nominations",
        // Category translations
        category: "Category",
        select_category: "Select a category",
        no_category: "No category",
        add_category: "Add category",
        create_category: "Create category",
        category_name_required: "Category name is required",
        category_created: "Category created successfully",
        category_create_error: "Error creating category",
        categories_load_error: "Error loading categories",
        category_name_placeholder: "Ex: Pop, Rock, Hip hop",
        slug: "Slug",
        slug_placeholder: "Ex: pop, rock, hip-hop",
        slug_help: "The slug is automatically generated from the name. You can modify it if necessary.",
        category_description_placeholder: "Category description (optional)",
        contest_type_auto_filled: "The contest type is automatically filled from the category",
        verification_requirements: "Verification Requirements",
        media_requirements: "Media Requirements",
        participant_individual: "Individual",
        participant_pet: "Pet",
        participant_club: "Club",
        verification_video_max_duration: "Max verification video duration (sec)",
        verification_max_size_mb: "Max verification size (MB)",
        new_participation: "New (Participation)",
        new_nomination: "New (Nomination)",
        min_images: "Min Images",
        max_images: "Max Images",
        min_age: "Min Age",
        max_age: "Max Age",
        max_videos: "Max Videos",
        video_max_duration: "Max video duration (sec)",
        video_max_size_mb: "Max video size (MB)",
        requires_video: "Video Required",
        kyc_required: "KYC Required",
        verification_visual: "Visual Verification",
        verification_voice: "Voice Verification",
        verification_brand: "Brand Verification",
        verification_content: "Content Verification"
      },
      contestants: {
        title: "Manage Contestants",
        description: "Approve or reject applications",
        search_placeholder: "Search by name or title...",
        all: "All",
        pending: "Pending",
        verified: "Verified",
        filter: "Filter",
        approve: "Approve",
        reject: "Reject",
        view: "View",
        author: "Author",
        images: "Images",
        videos: "Videos",
        votes: "Votes",
        comments: "Comments",
        status: "Status",
        registration_date: "Registration Date",
        actions: "Actions",
        contestant_details: "Contestant Details",
        close: "Close",
        no_contestants: "No contestants found",
        status_pending: "Pending",
        status_verified: "Verified",
        status_rejected: "Rejected",
        approve_success: "Contestant approved successfully",
        approve_error: "Error approving contestant",
        reject_success: "Contestant rejected successfully",
        reject_error: "Error rejecting contestant",
        status_update_success: "Contestant status updated successfully",
        status_update_error: "Error updating contestant status",
        comment_delete_success: "Comment deleted successfully",
        comment_delete_error: "Error deleting comment",
        comment_hide_success: "Comment hidden successfully",
        comment_hide_error: "Error hiding comment",
        comment_show_success: "Comment shown successfully",
        comment_show_error: "Error showing comment",
        comment_restore_success: "Comment restored successfully",
        comment_restore_error: "Error restoring comment",
        new_contestant: "New Contestant",
        edit_contestant: "Edit Contestant",
        user: "User",
        select_user: "Select a user",
        select_season: "Select a season",
        no_seasons_for_level: "No seasons available for this level",
        title_placeholder: "Contestant title",
        description_placeholder: "Contestant description",
        create_success: "Contestant created successfully",
        update_success: "Contestant updated successfully",
        save_error: "Error saving",
        seasons_load_error: "Error loading seasons",
        no_seasons_available: "No seasons available. Please create a season first."
      },
      categories: {
        title: "Category Management",
        description: "Create and manage contest categories",
        add_category: "Add category",
        search_placeholder: "Search for a category...",
        no_categories: "No categories yet",
        no_categories_found: "No categories found",
        created_at: "Created on",
        edit_category: "Edit category",
        create_category: "Create a new category",
        edit_category_description: "Edit category information",
        create_category_description: "Fill in the information to create a new category",
        category_name: "Name",
        category_name_required: "Name is required",
        category_name_max_length: "Name cannot exceed 100 characters",
        slug: "Slug",
        slug_required: "Slug is required",
        slug_max_length: "Slug cannot exceed 100 characters",
        slug_invalid: "Slug can only contain lowercase letters, numbers and hyphens",
        slug_auto_generated: "The slug is automatically generated from the name",
        description_label: "Description",
        description_placeholder: "Category description (optional)",
        is_active: "Active category",
        cancel: "Cancel",
        save: "Save",
        saving: "Saving...",
        edit: "Edit",
        create: "Create",
        delete: "Delete",
        delete_confirm: "Are you sure you want to delete the category",
        category_created: "Category created successfully",
        category_updated: "Category updated successfully",
        category_deleted: "Category deleted successfully",
        category_create_error: "Error creating category",
        category_update_error: "Error updating category",
        category_delete_error: "Error deleting category",
        categories_load_error: "Error loading categories"
      },
      kyc: {
        title: "Manage KYC",
        description: "Approve or reject identity verifications",
        search_placeholder: "Search by email or name...",
        pending: "Pending",
        approved: "Approved",
        rejected: "Rejected",
        filter: "Filter",
        approve: "Approve",
        reject: "Reject",
        view: "Details",
        no_kyc: "No KYC verifications found",
        verification_score: "Confidence Score",
        identity: "Identity",
        document: "Document",
        address: "Address",
        face: "Face",
        confidence_score: "Score",
        rejection_reason: "Rejection Reason"
      },
      reports: {
        title: "Report Management",
        description: "Manage content reports",
        search_placeholder: "Search for a report...",
        all: "All",
        pending: "Pending",
        reviewed: "Reviewed",
        resolved: "Resolved",
        no_reports: "No reports yet",
        no_reports_found: "No reports found",
        report_number: "Report #",
        reason: "Reason",
        description_label: "Description",
        status: "Status",
        details: "Details",
        reported_contestant: "Reported Contestant",
        contestant_author: "Contestant Author",
        reporter: "Reporter",
        contest: "Contest",
        created_at: "Created on",
        reviewed_at: "Reviewed on",
        moderator_notes: "Moderator Notes",
        verification_status: "Verification Status",
        verification_status_pending: "Pending",
        verification_status_approved: "Approved",
        verification_status_rejected: "Rejected",
        reason_spam: "Spam",
        reason_inappropriate: "Inappropriate content",
        reason_harassment: "Harassment",
        reason_fake: "Fake account",
        reason_copyright: "Copyright violation",
        reason_other: "Other",
        no_title: "No title",
        load_error: "Error loading reports",
        report_details: "Report Details",
        report_details_description: "Complete information about the report",
        reason_label: "Report Reason"
      },
      suggested_contests: {
        title: "Suggested Contests",
        description: "Manage contest suggestions submitted by users",
        search_placeholder: "Search for a suggestion...",
        all: "All",
        pending: "Pending",
        approved: "Approved",
        rejected: "Rejected",
        no_suggestions: "No suggestions yet",
        no_suggestions_found: "No suggestions found",
        author: "Author",
        author_not_available: "Author not available",
        unknown_date: "Unknown date",
        details: "Details",
        contest_suggestion_details: "Contest suggestion details",
        status: "Status",
        category: "Category",
        description: "Description",
        verified: "Verified",
        dates: "Dates",
        created_at: "Created on",
        updated_at: "Updated on",
        load_error: "Error loading suggestions"
      },
      transactions: {
        title: "Transaction Management",
        description: "View all transactions (deposits, withdrawals, etc.)",
        search_placeholder: "Search by reference, description, user...",
        all_types: "All types",
        all_statuses: "All statuses",
        no_transactions: "No transactions yet",
        no_transactions_found: "No transactions found",
        transaction: "Transaction",
        transaction_details: "Transaction Details",
        transaction_details_description: "Complete information about the transaction",
        type: {
          deposit: "Deposit",
          withdrawal: "Withdrawal",
          entry_fee: "Entry Fee",
          prize_payout: "Prize Payout",
          commission: "Commission",
          refund: "Refund"
        },
        status: {
          pending: "Pending",
          completed: "Completed",
          failed: "Failed",
          cancelled: "Cancelled"
        },
        user: "User",
        contest: "Contest",
        payment_method: "Payment Method",
        product_type: "Product Type",
        amount: "Amount",
        currency: "Currency",
        description: "Description",
        reference: "Reference",
        order_id: "Order ID",
        external_payment_id: "External Payment ID",
        tx_hash: "Transaction Hash",
        created_at: "Created on",
        processed_at: "Processed on",
        validated_at: "Validated on",
        type_label: "Type",
        status_label: "Status",
        details: "Details",
        search: "Search",
        load_error: "Error loading transactions"
      },
      accounting: {
        title: "Accounting",
        subtitle: "Financial overview and journal entries",
        refresh: "Refresh",
        total_revenue: "Total Revenue",
        ytd: "Year to date",
        journal_tab: "General Journal",
        coa_tab: "Chart of Accounts",
        journal_title: "Journal Entries",
        journal_desc: "Last 50 accounting entries",
        coa_title: "Chart of Accounts",
        coa_desc: "List of accounts and current balances",
        table: {
          date: "Date",
          ref: "Ref. No.",
          description: "Description",
          debit: "Debit",
          credit: "Credit",
          status: "Status",
          code: "Code",
          account: "Account Name",
          type: "Type",
          balance: "Balance"
        },
        error_loading: "Error loading accounting data",
        retry: "Retry",
        no_journal: "No journal entries yet.",
        no_coa: "No accounts in database. Run init_chart_of_accounts on the server.",
        reports_tab: "Financial reports",
        reports_hint:
          "General ledger, trial balance, balance sheet, income statement, and USDT (BSC) treasury summary.",
        load_report: "Load report",
        as_of_date: "As of",
        period_from: "From",
        period_to: "To",
        balance_sheet_title: "Balance sheet",
        income_statement_title: "Income statement",
        trial_balance_title: "Trial balance",
        cash_flow_title: "USDT (BSC) treasury summary",
        general_ledger_title: "General ledger (by account)",
        select_account: "Account",
        section_assets: "Assets",
        section_liabilities: "Liabilities",
        section_equity: "Equity",
        total_assets: "Total assets",
        total_liabilities: "Total liabilities",
        total_equity: "Total equity",
        balanced_ok: "Balanced: assets = liabilities + equity",
        balanced_no: "Difference (rounding or off–balance-sheet activity)",
        revenues: "Revenue",
        expenses: "Expenses",
        net_income: "Net income",
        statement_total_revenue: "Total revenue",
        statement_total_expenses: "Total expenses",
        total_debits: "Total debits",
        total_credits: "Total credits",
        trial_balanced: "Trial balance ties",
        trial_not_balanced: "Debit / credit mismatch",
        operating: "Operating activities",
        note: "Note",
        opening_balance: "Opening balance",
        closing_balance: "Closing balance",
        gl_lines: "Lines",
        no_report_data: "No data for this period.",
        report_failed: "Report failed",
        full_pack_tab: "Complete package",
        full_pack_hint:
          "Balance sheet, income statement, trial balance, USDT (BSC) treasury summary, full chart-of-accounts register, and period activity — all tied to your CoA and posted journals.",
        download_json: "Download JSON",
        download_coa_csv: "Download CoA CSV",
        summary_checks: "Checks",
        coa_register_title: "Chart of accounts register (all accounts)",
        period_activity_title: "Period activity by account",
        equity_highlights: "Equity (highlights)",
        parent_code: "Parent code",
        treasury_change_1001: "Change in USDT (BSC) treasury (1001)",
        cf_1001_opening: "Opening — USDT (BSC) treasury (1001)",
        cf_1001_closing: "Closing — USDT (BSC) treasury (1001)"
      },
      commission_settings: {
        subtitle: "Configure commission rules and rates",
        coming_soon: "This section is under development. Commission settings will be available soon."
      },
      microservices: {
        subtitle: "Manage and monitor microservices",
        coming_soon: "This section is under development. Microservices management will be available soon."
      },
      users: {
        title: "Manage Users",
        description: "Manage user roles and permissions",
        search_placeholder: "Search by email, name or username...",
        all: "All",
        admins: "Admins",
        verified: "Verified",
        inactive: "Inactive",
        filter: "Filter",
        table_user: "User",
        table_email: "Email",
        table_participations: "Participations",
        table_prizes: "Prizes",
        table_candidates: "Candidates",
        table_contests: "Contests",
        table_status: "Status",
        table_actions: "Actions",
        make_admin: "Make Admin",
        remove_admin: "Remove Admin",
        activate: "Activate",
        deactivate: "Deactivate",
        no_users: "No users found",
        registered: "Registered",
        inactive_status: "Inactive",
        user: "User",
        email: "Email",
        participations: "Participations",
        prizes: "Prizes",
        candidates: "Candidates",
        contests: "Contests",
        status: "Status",
        actions: "Actions",
        details: "Details",
        comments: "Comments",
        view_comments: "View Comments",
        no_comments: "No comments",
        comment_text: "Text",
        comment_date: "Date",
        comment_author: "Author",
        city: "City",
        country: "Country",
        continent: "Continent",
        region: "Region",
        kyc_status: "KYC Status",
        kyc_verified: "Verified",
        kyc_pending: "Pending",
        date_of_birth: "Date of Birth",
        phone: "Phone",
        bio: "Biography",
        last_login: "Last Login",
        joined: "Joined",
        participations_count: "Participations",
        prizes_count: "Prizes",
        contestants_count: "Candidates",
        contests_participated: "Contests",
        confirm_delete_title: "Delete User",
        confirm_delete_message: "Are you sure you want to delete this user? This action is irreversible.",
        delete: "Delete",
        cancel: "Cancel",
        delete_success: "User deleted successfully",
        delete_error: "Error deleting user",
        personal_info: "Personal Information",
        account_status: "Account Status",
        verify_kyc: "Verify KYC",
        unverify_kyc: "Revoke KYC",
        kyc_verify_success: "KYC verified successfully",
        kyc_unverify_success: "KYC verification revoked",
        toggle_admin_success: "Admin rights modified",
        toggle_admin_error: "Error modifying user role",
        toggle_active_success_deactivate: "User deactivated",
        toggle_active_success_activate: "User activated",
        toggle_active_error: "Error modifying user status",
        load_error: "Error loading users",
        load_details_error: "Error loading details",
        edit_comment: "Edit",
        delete_comment: "Delete",
        hide_comment: "Hide",
        show_comment: "Show",
        comment_edit_success: "Comment updated",
        comment_delete_success: "Comment deleted",
        comment_hide_success: "Comment hidden",
        comment_show_success: "Comment shown",
        comment_edit_error: "Error updating comment",
        comment_delete_error: "Error deleting comment",
        comment_hide_error: "Error hiding comment",
        comment_show_error: "Error showing comment",
        contest_label: "Contest",
        contestant_label: "Contestant"
      },
      reports: {
        title: "Reports",
        description: "Manage content reports",
        pending: "pending",
        reviewed: "reviewed",
        resolved: "resolved",
        search_placeholder: "Search by reason or type...",
        filter: "Filter",
        all: "All",
        no_reports: "No reports found",
        reporter: "Reporter",
        reported_content: "Reported Content",
        reason: "Reason",
        status: "Status",
        date: "Date",
        actions: "Actions",
        view: "View",
        mark_reviewed: "Mark as Reviewed",
        mark_resolved: "Mark as Resolved",
        details: "Details",
        close: "Close",
        report_details: "Report Details",
        reported_by: "Reported by",
        reported_at: "Reported at",
        report_reason: "Report Reason",
        report_description: "Description",
        report_status: "Status",
        moderator_notes: "Moderator Notes",
        reviewed_by: "Reviewed by",
        reviewed_at: "Reviewed at",
        content_type: "Content Type",
        contestant: "Contestant",
        comment: "Comment",
        media: "Media",
        user: "User",
        mark_reviewed_success: "Report marked as reviewed",
        mark_reviewed_error: "Error updating report",
        mark_resolved_success: "Report marked as resolved",
        mark_resolved_error: "Error updating report",
        load_error: "Error loading reports"
      }
    },
    hero: {
      badge: "World's #1 Contest Platform",
      title_line1: "Join the largest",
      title_line2: "contest Platform",
      title_line3: "in the world",
      subtitle: "Participate as a contestant, nominate your favorite contestant in your country, or vote in any contest you like, and get rewarded while having fun.",
      description: "Participate as a contestant, nominate your favorite contestant in your country, or vote in any contest you like, and get rewarded while having fun.",

      cta: "Get Started Now",
      demo: "Watch Demo",
      stats: {
        participants: "Active Participants",
        contests: "Contests Organized",
        countries: "Countries Represented"
      },
      trust: {
        secure: "Secure and Certified",
        support: "24/7 Support",
        free: "Free to Join"
      }
    },
    nav: {
      home: "Home",
      contests: "Contests",
      rankings: "Rankings",
      community: "Community",
      about: "About",
      login: "Login",
      register: "Sign Up"
    },
    navigation: {
      home: "Home",
      landing: "Landing",
      dashboard: "Dashboard",
      contests: "Contests",
      clubs: "Clubs",
      about: "About",
      contact: "Contact",
      login: "Login",
      register: "Sign Up",
      download_app: "Download App"
    },
    header: {
      language: "Language",
      theme: "Theme"
    },
    auth: {
      email: "Email",
      password: "Password",
      username: "Username",
      forgotPassword: "Forgot password?",
      loginError: "Login error",
      registerError: "Registration error",
      referral_detected: "Referral code detected!",
      referral_bonus: "You have been referred!",
      referral_code: "Code",
      login: {
        title: "Login",
        subtitle: "Sign in to your MyHigh5 account",
        email_placeholder: "Email or username",
        password_placeholder: "Your password",
        forgot_password: "Forgot password?",
        loading: "Signing in...",
        submit: "Sign In",
        no_account: "Don't have an account?",
        register_link: "Sign up",
        errors: {
          required_fields: "All fields are required",
          invalid_credentials: "Invalid email/username or password",
          timeout: "Request timed out. Please try again.",
          network_error: "Connection error. Please check your internet connection.",
          service_unavailable: "The service is starting up. Please wait a moment and try again."
        }
      },
      register: {
        title: "Sign Up",
        subtitle: "Create your free MyHigh5 account",
        email_placeholder: "Your email address",
        username_placeholder: "Username",
        username_hint: "Only letters, numbers, and underscores are allowed",
        username_no_spaces_warning: "Invalid characters",
        username_space_not_allowed: "Spaces are not allowed",
        password_requirements_title: "Password must contain:",
        password_requirement_length: "At least 8 characters",
        password_requirement_uppercase: "An uppercase letter (A-Z)",
        password_requirement_lowercase: "A lowercase letter (a-z)",
        password_requirement_number: "A number (0-9)",
        password_requirement_special: "A special character (*_/@=)",
        password_placeholder: "Password",
        confirm_password_placeholder: "Confirm password",
        full_name_placeholder: "Full name (optional)",
        phone_placeholder: "Phone number",
        referral_code_placeholder: "Referral code (optional)",
        country: "Country",
        country_placeholder: "Select a country",
        city: "City",
        city_placeholder: "Type your city",
        loading: "Creating account...",
        submit: "Create Account",
        have_account: "Already have an account?",
        login_link: "Sign in",
        terms_accept: "By signing up, you agree to our terms of service",
        success_title: "Registration Successful!",
        success_message: "Welcome! Your account has been created successfully.",
        continue_button: "Sign In",
        errors: {
          required_fields: "All required fields must be filled",
          password_mismatch: "Passwords do not match",
          password_min_length: "Password must be at least 8 characters",
          terms_required: "You must accept the terms of service",
          email_exists: "A user with this email already exists",
          username_exists: "This username is already taken",
          invalid_email: "Invalid email format",
          username_invalid_chars: "Only letters, numbers, and underscores are allowed",
          password_requirements: "Password must contain an uppercase letter, a lowercase letter, a number, and a special character (*_/@=)",
          location_required: "Please select your country and city"
        }
      },
      verify_email: {
        no_token: "Verification token missing",
        success: "Email verified successfully",
        error: "Error verifying email",
        verifying: "Verifying...",
        please_wait: "Please wait while we verify your email.",
        success_title: "Email verified!",
        redirecting: "Redirecting to login page...",
        error_title: "Verification error",
        invalid_token: "Invalid or expired token"
      },
      forgot_password: {
        title: "Forgot password?",
        description: "Enter your email address and we'll send you a link to reset your password.",
        email_required: "Email is required",
        send_reset_link: "Send reset link",
        success: "A reset email has been sent",
        success_title: "Email sent!",
        success_message: "If this email exists in our system, you will receive a password reset link.",
        check_spam: "Check your spam folder if you don't receive the email.",
        remember_password: "Remember your password?",
        error: "Error sending email"
      },
      reset_password: {
        title: "Reset password",
        description: "Enter your new password below.",
        no_token: "Reset token missing",
        password_required: "Password is required",
        password_min_length: "Password must be at least 6 characters",
        confirm_password_required: "Password confirmation is required",
        passwords_not_match: "Passwords do not match",
        new_password: "New password",
        confirm_password: "Confirm password",
        submit: "Reset password",
        success: "Password reset successfully",
        success_title: "Password reset!",
        success_message: "Your password has been reset successfully. You can now sign in.",
        redirecting: "Redirecting to login page...",
        error: "Error resetting password",
        invalid_token: "Invalid or expired token"
      }
    },
    common: {
      loading: "Loading...",
      error: "Error",
      success: "Success",
      network_error: "Connection error. Please check your internet connection.",
      cancel: "Cancel",
      confirm: "Confirm",
      continue: "Continue",
      or: "Or",
      redirecting: "Login successful! Redirecting to dashboard...",
      please_wait: "Please wait",
      back: "Back",
      back_to_dashboard: "Back to Dashboard",
      previous: "Previous",
      next: "Next",
      submitting: "Submitting...",
      no_documents: "No documents uploaded",
      profile_setup: "Profile Setup",
      profile_setup_description: "Complete your profile to participate in contests",
      edit: "Edit",
      delete: "Delete",
      deleting: "Deleting...",
      confirm_delete: "Confirm Delete",
      deleted_successfully: "Deleted successfully",
      likes: "Likes",
      comments: "Comments",
      search: "Search",
      clear: "Clear",
      optional: "optional",
      coming_soon: "Coming soon",
      welcome: "Welcome",
      access_denied: "Access Denied",
      no_permission: "You do not have permission to access this page.",
      refresh: "Refresh",
      view_more: "View more",
      unknown: "Unknown",
      load_more: "Load more",
      actions: "Actions"
    },
    affiliates: {
      grow_network: "Grow Your Network",
      invite_friends: "Invite friends and earn commissions on their activities",
      invite_now: "Invite Now",
      title: "Affiliate Program",
      your_link: "Your Affiliate Link",
      copy_link: "Copy Link",
      link_copied: "Link copied!",
      share: "Share",
      earnings: "Your Earnings",
      pending: "Pending",
      paid: "Paid",
      referrals: "Referrals",
    },
    profile_setup: {
      location: "Location",
      gender: "Gender",
      date_of_birth: "Date of Birth",
      male: "Male",
      female: "Female",
      other: "Other",
      prefer_not_to_say: "Prefer not to say",
      first_name: "First Name",
      first_name_placeholder: "Your first name",
      first_name_required: "First name is required",
      last_name: "Last Name",
      last_name_placeholder: "Your last name",
      last_name_required: "Last name is required",
      avatar: "Avatar",
      avatar_required: "Avatar is required",
      bio: "Bio",
      bio_placeholder: "Tell us about yourself...",
      bio_required: "Bio is required",
      characters: "characters",
      city_required: "City is required",
      continent_required: "Continent is required",
      region_required: "Region is required",
      country_required: "Country is required",
      gender_required: "Gender is required",
      dob_required: "Date of birth is required",
      session_expired: "Session expired",
      update_error: "Error updating profile",
      success: "Profile configured successfully!",
      continue: "Continue",
      info: "This information is required to participate in contests. You can modify it later in your profile settings.",
      click_upload: "Click to upload",
      preparing: "Preparing...",
      checking_files: "Checking files...",
      uploading: "Uploading...",
      images: "Images",
      upload_error: "Upload error"
    },
    settings: {
      title: "Settings",
      description: "Manage your personal information and preferences",
      profile: "Profile",
      profile_short: "Photo, name and bio",
      profile_description: "Edit your photo, name and biography",
      location: "Location",
      location_short: "Country and city",
      location_description: "Set your geographic location",
      demographics: "Identity",
      demographics_short: "Gender and age",
      demographics_description: "Enter your personal information",
      continent: "Continent",
      region: "Region",
      country: "Country",
      city: "City",
      current_location: "Current Location",
      location_locked_title: "Location Locked",
      location_locked_message: "You have already participated in a contest. Your location cannot be modified.",
      save: "Save",
      remove: "Remove",
      profile_completion: "Profile completed",
      missing: "Missing",
      referral_code_label: "Referral code",
      admin: "Admin",
      verified: "Verified",
      verify_identity: "Verify my identity",
      years: "years",
      user: "User",
      profile_photo: "Profile photo",
      biography: "Biography",
      password: {
        title: "Password",
        description: "Change your password to secure your account",
        current: "Current password",
        new: "New password",
        confirm: "Confirm new password",
        current_required: "Current password is required",
        new_required: "New password is required",
        confirm_required: "Password confirmation is required",
        min_length: "Password must be at least 6 characters",
        mismatch: "Passwords do not match",
        same_password: "New password must be different from the old one",
        session_expired: "Session expired",
        success: "Password changed successfully",
        error: "Error changing password",
        saving: "Saving...",
        save: "Change password",
        security_info: "Account security",
        security_description: "To protect your account, use a strong and unique password.",
        min_6_chars: "6 characters minimum",
        uppercase: "One uppercase",
        lowercase: "One lowercase",
        number: "One number"
      },
      password_short: "Account security"
    },
    participation: {
      location: "Your Location",
      category: "Category",
      categoryPlaceholder: "Select a category",
      title: "Title",
      title_placeholder: "Enter your entry title",
      description: "Description",
      descriptionPlaceholder: "Describe your entry, talents, achievements...",
      characters: "characters",
      media: "Media (Images/Videos)",
      images: "Images",
      images_placeholder: "Click to add images",
      video: "Video",
      video_placeholder: "Click to add a video",
      video_optional: "Video (optional)",
      clickUpload: "Click or drag your files",
      preparing: "Preparing...",
      checkingFiles: "Checking files...",
      uploading: "Uploading...",
      imagesVideos: "Images and videos",
      uploadError: "Upload error",
      uploadedFiles: "Uploaded files",
      submit: "Submit my entry",
      cancel: "Cancel",
      profile_incomplete_title: "⚠️ Incomplete Profile",
      profile_incomplete_message: "You must complete your profile before participating in contests. Please provide your first name, last name, country and city.",
      complete_profile_button: "Complete My Profile",
      kyc_notification: "⚠️ Your identity has not been verified. We recommend completing your KYC verification for a better experience.",
      // URL import
      or: "or",
      add_by_url: "Add by URL",
      add_video_by_url: "Add by URL",
      add: "Add",
      image_url_placeholder: "https://example.com/image.jpg",
      video_url_placeholder: "https://youtube.com/watch?v=... or https://example.com/video.mp4",
      invalid_video_url: "Unauthorized link. Only YouTube and TikTok are accepted.",
      unsupported_platform: "Unauthorized link",
      open_link: "Open link",
      view_on_tiktok: "View on TikTok",
      view_on_youtube: "View on YouTube",
      only_youtube_tiktok: "Only YouTube and TikTok are accepted",
      invalid_url: "Invalid video URL",
      video_platform_not_allowed: "This video platform is not accepted. Only YouTube and TikTok are supported.",
      video_file_not_allowed: "Video file uploads are not allowed. Please use a YouTube or TikTok URL.",
      youtube_shorts_not_allowed: "YouTube Shorts are not allowed. Please use a standard YouTube video.",
      tiktok_preview_unavailable: "Preview unavailable — watch on TikTok",
      watch_on_tiktok: "Watch on TikTok",
      url_required: "URL required",
      invalid_url: "Invalid URL",
      max_images_reached: "Maximum number of images reached",
      image_added: "Image added",
      video_added: "Video added",
      // Media requirements
      media_requirements: "Media requirements",
      images_required: "Images",
      video_required: "Video required",
      video_required_title: "Video *",
      // New labels
      content_title: "Content Title",
      content_title_placeholder: "Enter content title (minimum 10 characters)",
      content_description: "Content Description",
      content_description_placeholder: "Enter content description (20-50 characters)",
      content_image: "Content Image",
      content_video_required: "Content Video *",
      content_video_optional: "Content Video (optional)",
      min_characters: "Minimum",
      important_errors: "Important Errors to Fix",
      // Nominator location fields
      nominator_location: "Contestant Location",
      nominator_location_description: "Please provide the location of the person you are nominating.",
      nominator_country: "Country",
      nominator_country_note: "The country must match your profile country. You can only nominate contestants from your own country.",
      select_country: "Select a country",
      nominator_city: "City",
      nominator_city_placeholder: "Enter the city name",
      select_city: "Select a city",
      select_country_first: "Select a country first",
      ad_revenue_warning: "Warning: You will not be paid for ad revenue generated by your content if we detect that the content does not originate from your country.",
      // Stepper
      step_info: "Information",
      step_media: "Media",
      step_review: "Review",
      time_remaining: "Remaining participation time",
      deadline: "Deadline",
      submission_period_ended: "The submission period has ended",
      review_title: "Review your submission",
      supported_platforms: "Supported platforms",
      unrecognized_video_link: "Unrecognized video link",
      // Errors
      errors: {
        content_title_required: "Content Title",
        content_title_min_length: "Content title must contain at least 5 characters",
        content_title_max_length: "Content title must not exceed 5 characters",
        content_description_required: "Content Description",
        content_description_min_length: "Content description must contain at least 20 characters",
        content_description_max_length: "Content description must not exceed 50 characters",
        content_image_required: "Content Image",
        at_least_one_image: "At least one image is required",
        content_video_required: "Content Video",
        video_required_for_contest: "A video is required for this contest",
        fill_all_fields: "Please fill in all required fields before submitting",
        nominator_country_required: "Country is required"
      }
    },
    moderation: {
      content_rejected: "⚠️ Content rejected by moderation",
      adult_content: "Adult content detected",
      violence_detected: "Violent content detected",
      gore_detected: "Gore/bloody content detected",
      weapons_detected: "Weapon detected",
      offensive_content: "Offensive content detected",
      ownership_failed: "Ownership verification failed",
      face_mismatch: "Face does not match your verification",
      analyzing: "Analyzing content...",
      approved: "Content approved",
      rejected: "Content rejected"
    },
    features: {
      title: "Exceptional Features",
      subtitle: "Discover everything that makes MyHigh5 a unique and exciting global online contest platform.",
      items: {
        multi_level: {
          title: "Multi-Level Contests",
          description: "Participate in local, national and international competitions with a unique progression system."
        },
        financial_rewards: {
          title: "Financial Rewards",
          description: "Get paid affiliate commissions from revenues generated by your referral network, up to 10 generations deep."
        },
        international_reach: {
          title: "International Reach",
          description: "Your talents can be discovered and appreciated by a diverse global audience."
        },
        innovative_voting: {
          title: "Innovative Voting",
          description: "Fair and transparent voting system with real-time rankings."
        },
        varied_categories: {
          title: "Varied Categories",
          description: "Find the contest categories that excite you to participate. Recommend any missing categories you would like to see added."
        }
      }
    },
    contestant_detail: {
      about: "About",
      gallery: "Gallery",
      photos: "Photos",
      images: "Images",
      videos: "Videos",
      votes: "Votes",
      rank: "Rank",
      contest_info: "Contest",
      candidate_info: "Entry",
      title: "Title",
      participants: "Participants",
      registered_on: "Registered on",
      status: "Status",
      qualified: "✓ Qualified",
      pending: "⏳ Pending",
      confirm_vote: "Confirm your vote",
      vote_confirmation: "Are you sure you want to vote for",
      are_you_sure: "?",
      cancel: "Cancel",
      vote: "Vote",
      voted: "Voted",
      voting: "Voting...",
      cover_image: "Cover image",
      vote_error: "Error voting. Please try again.",
      vote_success: "You voted successfully! ✨",
      add_reaction: "Add a reaction",
      react: "React",
      like: "Like",
      love: "Love",
      wow: "Wow",
      dislike: "Dislike",
      vote_history: "Vote History",
      no_votes: "No votes yet",
      voted_for: "Voted for",
      reaction: "Reaction",
      comment: "Comment",
      date: "Date",
      comments: "Comments",
      add_comment: "Add a comment",
      comment_placeholder: "Write your comment...",
      comment_on_photo: "Comment on this photo",
      comment_on_video: "Comment on this video",
      comment_on_contest: "Comment on this contest",
      no_comments: "No comments yet",
      comment_posted: "Comment posted successfully! ✨",
      comment_error: "Error posting comment",
      comments_count: "Comments",
      reply: "Reply",
      reply_placeholder: "Write your reply...",
      like_comment: "Like",
      media_preview: "Media Preview",
      close: "Close",
      of: "of",
      contestant_label: "Contestant",
      nominator_label: "Nominator",
      nominated_for: "Nominated for:",
      contest_rank_label: "Ranking",
      description_section: "Description",
      candidacy_id: "Candidacy ID",
      season_label: "Season",
      entry_fallback_title: "Application",
      full_description: "Full description"
    },
    testimonials: {
      title: "What our users say",
      favorites: {
        title: "My Favorites",
        description: "View your favorite contests and contestants",
        description_contestants: "Organize your favorite contestants by drag and drop",
        contests_tab: "Contests",
        contestants_tab: "Contestants",
        no_favorite_contests: "You don't have any favorite contests yet",
        no_favorite_contestants: "You don't have any favorite contestants yet",
        no_favorites_yet: "No favorites yet",
        no_favorites_hint: "Add contestants to your favorites from a contest page by clicking the star.",
        browse_contests: "Browse contests"
      },
      myhigh5: {
        title: "MyHigh5",
        description: "The 5 contestants you have voted for",
        hint: "Your first vote is displayed in position 1, and your most recent vote in position 5. You can vote for a maximum of 5 contestants.",
        no_votes: "No votes yet",
        no_votes_description: "You haven't voted for any contestants yet. Explore contests to vote!",
        explore_contests: "Explore contests",
        explore_more: "Explore more contests",
        remaining_votes: "You can still vote for {count} more contestant(s)",
        votes_label: "votes",
        hint_dnd: "Drag and drop to reorder your votes. 1st place gets 5 points, 2nd gets 4 points, 3rd gets 3 points, 4th gets 2 points, and 5th gets 1 point. You may vote for as many contestants as you wish, but only the top 5 are counted for voting credit. Any additional vote after the fifth will replace the contestant currently in 5th place..",
        rank: "Rank",
        points: "Points",
        contestant: "Contestant",
        location: "Location",
        total_votes: "Total votes",
        vote_date: "Vote date",
        order_saved: "Order saved!",
        order_error: "Error saving order",
        points_legend: "Points system",
        points_label: "points"
      },
      subtitle: "Join thousands of satisfied participants who have transformed their passion into success.",
      cta: "Join thousands of satisfied participants",
      users: "+1M users",
      items: {
        marie: {
          name: "Marie Dubois",
          text: "MyHigh5 allowed me to discover my talent and meet an incredible community. I won 3 contests this year!",
          role: "Beauty Contest Winner",
          rating: 5,
          location: "Paris, France"
        },
        jean: {
          name: "Jean Martin",
          text: "The interface is intuitive and the contests are varied. It has become my favorite platform to express my creativity.",
          role: "Active Participant",
          rating: 5,
          location: "Lyon, France"
        },
        sophie: {
          name: "Sophie Laurent",
          text: "Thanks to the affiliate program, I created an additional source of income while having fun.",
          role: "MyHigh5 Ambassador",
          rating: 5,
          location: "Marseille, France"
        },
        sarah_m: {
          name: "Sarah Martin",
          text: "An incredible experience! I discovered my passion for photography through MyHigh5 contests.",
          role: "Amateur Photographer",
          rating: 5,
          location: "London, UK"
        },
        carlos_r: {
          name: "Carlos Rodriguez",
          text: "The community is fantastic and very encouraging. My dance talents have been recognized internationally!",
          role: "Professional Dancer",
          rating: 5,
          location: "Madrid, Spain"
        },
        emma_l: {
          name: "Emma Laurent",
          text: "MyHigh5 gave me the confidence to share my creations. Now I have my own online store!",
          role: "Creative Artist",
          rating: 5,
          location: "Brussels, Belgium"
        }
      }
    },
    cta: {
      title: "Ready to start your adventure?",
      subtitle: "Join millions of participants and discover your potential today.",
      button: "Create my free account",
      features: {
        instant: "Instant registration",
        global: "Global community",
        secure: "100% secure",
        free_contests: "Free contests",
        active_community: "Active community",
        real_rewards: "Real rewards"
      },
      trust: {
        instant: "Registration in 30 seconds",
        secure: "No credit card required",
        support: "24/7 Support"
      }
    },
    landing: {
      ways_to_earn: {
        badge: "Earn Money",
        title: "Different Ways to Earn",
        subtitle: "Join our affiliate program and earn commissions on multiple revenue streams",
        kyc_payments: {
          title: "KYC Payments",
          description: "Earn commissions when members in your network complete their KYC verification",
          commission: "10% on Level 1, 1% on Levels 2-10"
        },
        founding_membership: {
          title: "Founding Membership",
          description: "Earn commissions when members in your referral network join Founding Members Club or pay for annual membership fee.",
          commission: "10% on Level 1, 1% on Levels 2-10"
        },
        annual_membership: {
          title: "Annual Membership Fee",
          description: "Earn commissions when Founding Members pay their annual membership fee.",
          commission: "10% on Level 1, 1% on Levels 2-10"
        },
        club_memberships: {
          title: "Club Memberships",
          description: "Earn commissions on paid club membership fees. The website adds a 20% markup to the club owner's specified fees, of which 10% is paid to Level 1, and 1% is paid to each of Levels 2 through 10.",
          commission: "10% on Level 1, 1% on Levels 2-10"
        },
        shop_purchases: {
          title: "Shop Purchases",
          description: "Earn commissions on digital content purchases in the MyHigh5 shop. The website adds a 20% markup to the club owner's specified fees, of which 10% is paid to Level 1, and 1% is paid to each of Levels 2 through 10.",
          commission: "10% on Level 1, 1% on Levels 2-10"
        },
        ad_revenue: {
          title: "Ad Revenue Sharing",
          description: "Contest participants earn 40% of the advertising revenue generated on their contest pages. Their Level 1 sponsors earn 5%, and Levels 2 through 10 earn 1% each. Contest nominators earn 10% of the advertising revenue generated by their nominated contestants. Their Level 1 sponsors earn 2.5%, and Levels 2 through 10 earn 1% each.",
          commission: "Participants: 40% for self, 5% for Level 1, 1% for each of Levels 2 to 10.\nNominators: 10% for self, 2.5% for Level 1, 1% for each of Levels 2 to 10."
        },
        ad_campaigns: {
          title: "Website Sponsors Page",
          description: "Level 1 sponsors earn a 10% commission, and Levels 2 through 10 earn 1% each.",
          commission: "10% on Level 1, 1% on Levels 2-10"
        }
      },
      faq: {
        badge: "Frequently Asked Questions",
        title: "Frequently Asked Questions",
        subtitle: "Find answers to the most common questions about MyHigh5",
        question_1: "How can I earn money on MyHigh5?",
        answer_1: "You can earn money in several ways: by participating in contests, by nominating contestants, by joining the affiliate program to earn commissions on members you refer, and by becoming a founding member to participate in revenue and profit pools.",
        question_2: "How does the affiliate program work?",
        answer_2: "• Verification Fee Payments:\n  You earn a 10% commission on payments made by your direct referrals, and a 1% commission on payments made by each of your indirect referrals from Level 2 to Level 10.\n\n• Ad Revenue (Participating Contestants):\n  Participating contestants receive 40% of the ad revenue generated on their contest pages. The direct sponsor of a participating contestant receives 5%, and each indirect sponsor from Level 2 to Level 10 receives 1%.\n\n• Ad Revenue (Nominating Members):\n  Nominating members receive 10% of the ad revenue generated on the contest pages of their nominated contestants, 2.5% of the ad revenue generated on the contest pages of contestants nominated by their direct referrals, and 1% of the ad revenue generated on the contest pages of contestants nominated by each of their indirect referrals from Level 2 to Level 10.\n\n• Ad Revenue (Clubs):\n  Club owners receive 20% of the ad revenue generated on their club or fan pages. The direct sponsor of a club owner receives 5%, and each indirect sponsor from Level 2 to Level 10 receives 0.5%.\n\n• Club Membership Fees:\n  MyHigh5 applies a 20% markup to the member's selected subscription fee. Of this markup, 10% is paid to the direct sponsor of the payer, and 1% is paid to each indirect sponsor from Level 2 to Level 10.\n\n• Website Sponsors Page Slots:\n  For slots paid for on the Website Sponsors page, 10% is paid to the Level 1 sponsor, and 1% is paid to each of the Level 2 through Level 10 sponsors.",
        question_3: "What is the Founding Member status?",
        answer_3: "Founding Member (MFM) status is a limited opportunity that requires account verification and payment of a joining fee of $100 and an annual club membership fee of $50 for the first 1,000 MFMs, and a joining fee of $200 and an annual club membership fee of $200 thereafter. MFM slots will cease to exist once the total number of MFMs reaches 10,000. Founding Members participate in monthly commission pools equal to 5% of net revenues and an annual profit pool equal to 10% of profits after taxes, allocated based on the proportion of their Level 1 verified referrals relative to the total number of Level 1 verified referrals.",
        question_4: "How can I participate in contests?",
        answer_4: "To participate in contests, you need to create a free account, complete your profile, and submit your application with photos or videos according to the contest requirements. Some contests may require KYC verification.",
        question_5: "Are contests free?",
        answer_5: "Yes. Contest participation is free, but your account must be verified because we need to match your participation content with your verified identity. You do not need to verify your account in order to nominate contestants.",
        question_6: "How can I withdraw my earnings?",
        answer_6: "You can withdraw your earnings through your wallet in the dashboard. Payments are processed monthly, with a minimum payout threshold of $100. Payment methods include bank transfer, PayPal, or cryptocurrency."
      },
      download_app: {
        badge: "Mobile App",
        title: "Download the MyHigh5 App",
        subtitle: "Participate in contests, vote and earn money wherever you are with our mobile app",
        scan_qr: "Scan to download",
        download_on: "Download on",
        app_store: "App Store",
        available_on: "Available on",
        google_play: "Google Play",
        access_24_7: "24/7 Access",
        free: "Free"
      }
    },
    footer: {
      description: "The world's most popular contest platform. Participate, vote and win in exciting competitions.",
      copyright: " 2024 MyHigh5. All rights reserved.",
      newsletter: {
        title: "Stay Updated on New Contests",
        subtitle: "Receive the latest news and opportunities directly in your inbox.",
        placeholder: "Your email address",
        subscribe: "Subscribe",
        terms: "By subscribing, you agree to our terms of use and privacy policy."
      },
      brand: {
        countries: "Available in 200+ countries",
        support: "24/7 Support",
        email: "infos@myhigh5.com"
      },
      quick_links: {
        title: "Quick Links",
        about: "About",
        contests: "Contests",
        how_it_works: "How it works",
        affiliate: "Affiliate program",
        support: "Support"
      },
      categories: {
        title: "Categories",
        beauty: "Beauty Contests",
        handsome: "Handsome Contests",
        latest_hits: "Latest Hits",
        pets: "Pets",
        sports_clubs: "Sports Clubs",
        no_categories: "No categories available"
      },
      legal: {
        title: "Legal",
        privacy: "Privacy Policy",
        terms: "Terms of Service",
        cookies: "Cookie Policy",
        gdpr: "GDPR Compliance"
      }
    },
    dashboard: {
      welcome: "Welcome",
      subtitle: "Discover your personalized dashboard",
      search: {
        placeholder: "Search...",
        title: " Search",
        description: "Find contests, contestants, clubs and products",
        no_results: "No results found",
        start_typing: "Start typing to search...",
        contest: "Contest",
        contestant: "Contestant",
        club: "Club",
        product: "Product",
        recent_searches: "Recent searches",
        no_history: "No recent searches."
      },
      nav: {
        home: "Home",
        overview: "Overview",
        feed: "Feed",
        contests: "Contests",
        groups: "Groups",
        my_applications: "My Applications",
        clubs: "Clubs",
        myhigh5: "MyHigh5",
        favorites: "Favorites",
        messages: "Messages",
        following: "Following",
        social: "Social",
        search: "Search",
        pages: "Pages",
        wallet: "Wallet",
        affiliates: "Affiliates",
        commissions: "Commissions",
        leaderboard: "Leaderboard",
        prize: "Prize",
        shop: "Shop",
        main: "Main",
        competitions: "Competitions",
        business: "Business",
        resources: "Resources",
        founding_member: "Founding Membership",
        affiliate_program: "Affiliate Program",
        affiliate_agreement: "Affiliate Agreement",
        account: "Account",
        settings: "Settings",
        admin: "Administration",
        admin_panel: "Admin Panel",
        admin_panel_desc: "Manage the platform",
        notifications: "Notifications",
        notifications_desc: "View all your notifications"
      },
      feed: {
        welcome: "Welcome to your feed!",
        welcome_description: "Start following people to see their posts here.",
        create_first_post: "Create your first post",
        loading: "Loading...",
        load_more: "Load more",
        create_post: "Create a post",
        delete_confirm: "Are you sure you want to delete this post?",
        create_post_placeholder: "What's on your mind?",
        media: "Media",
        video: "Video",
        poll: "Poll",
        emoji: "Emoji",
        schedule: "Schedule",
        location: "Location",
        publish: "Publish",
        delete: "Delete",
        report: "Report",
        suggested_users: "Suggestions for you",
        suggested_groups: "Suggested groups",
        see_more: "See more",
        ad_title: "Discover premium features",
        ad_description: "Access exclusive features and boost your visibility",
        ad_cta: "Learn more",
        create_post_dialog_title: "Create a post",
        publishing: "Publishing...",
        post_tab: "Post",
        poll_tab: "Poll",
        post_placeholder: "What's on your mind?",
        files_selected: "file(s) selected",
        poll_question_placeholder: "Ask your question...",
        poll_options_label: "Poll options",
        poll_option_placeholder: "Option",
        add_poll_option: "Add an option",
        public_visibility: "Public",
        followers_visibility: "Followers",
        private_visibility: "Private",
        comments: "Comments",
        no_comments: "No comments",
        add_comment_placeholder: "Add a comment...",
        comment_shortcut: "Ctrl+Enter to post",
        posting: "Posting...",
        post: "Post",
        comment_success: "Comment posted successfully!",
        comment_error: "Failed to post comment. Please try again.",
        post_success: "Post created successfully!",
        post_error: "Failed to create post. Please try again.",
        link_copied: "Link copied to clipboard",
        share_failed: "Could not open share. Try copying the link.",
        repost_failed: "Could not record repost. Please try again.",
        repost: "Repost",
        share: "Share"
      },
      messages: {
        title: "Messages",
        subtitle: "End-to-end encrypted messages",
        no_conversations: "No conversations",
        start_conversation: "Start a new conversation",
        encrypted_message: "Encrypted message",
        end_to_end_encrypted: "End-to-end encrypted",
        type_message: "Type a message...",
        select_conversation: "Select a conversation",
        select_conversation_desc: "Choose a conversation to start chatting",
        message_button: "Message",
        new_message: "Start a new message"
      },
      groups: {
        title: "Groups",
        subtitle: "Join groups and share with your community",
        search_placeholder: "Search for a group...",
        no_groups_found: "No groups found",
        no_groups_available: "No groups available",
        try_keywords: "Try different keywords",
        be_first: "Be the first to create a group!",
        create_group: "Create a group",
        members: "members",
        no_members: "No members yet",
        no_messages: "No messages yet",
        join_to_chat: "Join the group to start chatting",
        created_by: "Created by",
        leave: "Leave",
        join: "Join",
        create_new_group: "Create a new group",
        group_name: "Group name",
        group_name_placeholder: "Group name",
        description: "Description",
        description_placeholder: "Group description (optional)",
        group_type: "Group type",
        public: "Public",
        private: "Private",
        cancel: "Cancel",
        creating: "Creating...",
        create_group_button: "Create group"
      },
      following: {
        title: "Social Network",
        subtitle: "Manage your following and discover new users",
        following_tab: "Following",
        followers_tab: "Followers",
        suggested_tab: "Suggested",
        search_placeholder: "Search...",
        no_users_found: "No users found",
        no_users: "No users",
        followers: "followers",
        posts: "posts",
        unfollow: "Unfollow",
        follow: "Follow"
      },
      stats: {
        contests: "My Contests",
        clubs: "My Clubs",
        favorites: "My Favorites",
        points: "My Points"
      },
      analytics: {
        hello: "Hello",
        overview: "Here's an overview of your performance",
        performance: "Performance",
        affiliates: "Affiliates",
        total_votes: "Votes",
        likes: "Likes",
        comments: "Comments",
        total_views: "Views",
        reactions: "Reactions",
        direct_affiliates: "Direct Affiliates",
        total_network: "Total Network",
        commissions: "Commissions",
        conversion_rate: "Conversion Rate",
        contest_performance: "Contest Performance",
        contest_performance_desc: "Votes and engagement of your applications",
        reactions_distribution: "Reactions",
        reactions_distribution_desc: "Distribution by type",
        weekly_activity: "Weekly Activity",
        weekly_activity_desc: "Votes and views this week",
        network_growth: "Network Growth",
        network_growth_desc: "Evolution of your affiliates",
        monthly_commissions: "Monthly Commissions",
        monthly_commissions_desc: "Revenue generated by your network",
        active_contests: "Active Contests",
        best_ranking: "Best Ranking",
        engagement: "Engagement",
        this_month: "This month",
        total: "Total",
        last_7_days: "7 days",
        view_stats: "View statistics",
        statistics: "Statistics",
        days: {
          monday: "Monday",
          tuesday: "Tuesday",
          wednesday: "Wednesday",
          thursday: "Thursday",
          friday: "Friday",
          saturday: "Saturday",
          sunday: "Sunday",
          mon: "Mon",
          tue: "Tue",
          wed: "Wed",
          thu: "Thu",
          fri: "Fri",
          sat: "Sat",
          sun: "Sun"
        },
        months: {
          january: "January",
          february: "February",
          march: "March",
          april: "April",
          may: "May",
          june: "June",
          july: "July",
          august: "August",
          september: "September",
          october: "October",
          november: "November",
          december: "December",
          jan: "Jan",
          feb: "Feb",
          mar: "Mar",
          apr: "Apr",
          may_short: "May",
          jun: "Jun",
          jul: "Jul",
          aug: "Aug",
          sep: "Sep",
          oct: "Oct",
          nov: "Nov",
          dec: "Dec"
        }
      },
      wallet: {
        title: "My Wallet",
        subtitle: "Manage your earnings and transactions",
        available_balance: "Available balance",
        pending_balance: "Pending",
        pending_description: "Funds being validated",
        total_earnings: "Total earnings",
        since_registration: "Since registration",
        this_month: "This month",
        history: "History",
        withdraw: "Withdraw",
        recent_transactions: "Recent transactions",
        all_transactions: "All transactions",
        transactions_subtitle: "Complete history of your transactions",
        see_all: "See all",
        completed: "Paid",
        approved: "Approved",
        pending: "Pending",
        failed: "Failed",
        expired: "Expired",
        commission: "Commission",
        purchase: "Purchase",
        all: "All",
        commissions: "Commissions",
        purchases: "Purchases",
        filter_by_type: "Filter by type",
        export: "Export",
        no_transactions: "No transactions",
        no_transactions_desc: "You don't have any transactions yet",
        pay: "Pay",
        invoice: "Invoice",
        download_invoice: "Download invoice",
        buy_service: "Buy a service"
      },
      affiliates: {
        title: "Affiliate Program",
        subtitle: "Refer and earn commissions",
        invite: "Invite",
        total_affiliates: "Total affiliates",
        direct_affiliates: "Direct affiliates",
        total_commissions: "Commissions",
        conversion_rate: "Conversion rate",
        your_referral_link: "Your referral link",
        your_referral_links: "Your referral links",
        link_register: "Registration link",
        link_home: "Homepage link",
        link_contestants: "Contests page link",
        your_code: "Your code",
        copy: "Copy",
        copied: "Copied!",
        share: "Share",
        view_links: "View links",
        share_description: "Share your links and earn commissions on each registration",
        links_description: "Copy and share these links to refer new users",
        your_sponsor: "Your sponsor",
        no_sponsor: "No sponsor",
        commission_tiers: "Commission tiers",
        commission_description: "Discover our 10 commission levels",
        view_commissions: "View details",
        total_potential: "Total potential",
        max_commission: "Maximum commission over 10 levels",
        level: "Level",
        direct_referrals: "Direct referrals",
        second_level: "Second level",
        third_level: "Third level",
        your_affiliates: "Your affiliates",
        see_all: "See all",
        active: "Active",
        joined: "Joined",
        earnings: "Earnings generated",
        no_affiliates: "No affiliates yet",
        start_inviting: "Start inviting friends to earn commissions",
        invite_friends: "Invite friends",
        ten_levels: "10 commission levels",
        commission: "Commission",
        no_commission: "No commission",
        kyc_pending: "KYC pending",
        commission_rate: "10% on KYC payments",
        commission_structure: "KYC Commission Structure",
        all_kyc_statuses: "All KYC",
        kyc_status_label: "KYC Status",
        kyc_none: "Not started",
        kyc_in_progress: "In progress",
        kyc_approved: "Verified",
        kyc_rejected: "Rejected",
        kyc_expired: "Expired",
        kyc_requires_review: "Needs review",
        kyc_verified: "KYC Verified",
        direct_referrals: "Direct (Lvl. 1)",
        indirect_referrals: "Indirect (Lvl. 2-10)",
        direct_tooltip_title: "Direct Referrals",
        direct_tooltip_desc: "Users you directly referred (level 1). You earn 10% commission on their KYC payments.",
        indirect_tooltip_title: "Indirect Referrals",
        indirect_tooltip_desc: "Users referred by your referrals (levels 2-10). You earn 1% commission on their KYC payments.",
        earned: "Earned",
        total_tooltip_title: "Total Affiliates",
        total_tooltip_desc: "Total number of people in your affiliate network, all levels combined (1 to 10).",
        active_tooltip_title: "Active Affiliates",
        active_tooltip_desc: "Users with an active account who can generate commissions.",
        kyc_verified_tooltip_title: "KYC Verified",
        kyc_verified_tooltip_desc: "Affiliates who have successfully completed identity verification (KYC approved).",
        commissions_tooltip_title: "Total Commissions",
        commissions_tooltip_desc: "Sum of all commissions earned through your affiliate network.",
        col_affiliate_hint: "Information about the member in your network",
        col_level_hint: "Level 1 = direct (10%), Levels 2-10 = indirect (1%)",
        col_kyc_hint: "Identity verification status (commission received if approved)",
        col_referrals_hint: "Number of people referred by this affiliate",
        col_earnings_hint: "Commission you earned from this affiliate",
        col_status_hint: "User account status (active or inactive)",
        levels: "Levels",
        direct_commission: "Direct commission",
        indirect_commission: "Indirect commissions",
        indirect_description: "Earn 1% on each level of your network, up to the 10th level.",
        cookie_tracking: "Cookie tracking: 30 days",
        all_affiliates: "All affiliates",
        affiliates_found: "affiliates found",
        search_placeholder: "Search by name or email...",
        all_levels: "All levels",
        all_statuses: "All statuses",
        inactive: "Inactive",
        affiliate: "Affiliate",
        referrals_count: "Referrals",
        status: "Status",
        total_referrals: "Total referrals",
        no_results: "No results",
        try_different_filters: "Try different filters",
        showing: "Showing",
        of: "of",
        // Invitations
        pending_invitations: "Pending",
        invite_friend: "Invite a friend",
        invite_description: "Send an email invitation to refer your friends",
        email_address: "Email address",
        personal_message: "Personal message",
        message_placeholder: "Hi! Join me on MyHigh5...",
        send_invitation: "Send invitation",
        sending: "Sending...",
        share_link: "Share your link",
        code_label: "Code",
        link_copied: "Link copied!",
        invite_sent_success: "Invitation sent successfully!",
        invite_error: "Error sending invitation",
        invite_email_required: "Please enter an email",
        pending: "Pending",
        sent_on: "Sent on",
        cancel: "Cancel",
        invitation_cancelled: "Invitation cancelled",
        no_pending: "No pending invitations",
        send_invitation_desc: "Send invitations to your friends to refer them",
        copy_error: "Error copying",
        cancel_error: "Error cancelling"
      },
      commissions: {
        title: "My Commissions",
        subtitle: "Track your earnings and affiliate revenue",
        export: "Export",
        total_earned: "Total Earned",
        pending: "Pending",
        pending_amount: "Pending Amount",
        paid: "Paid",
        paid_amount: "Paid Amount",
        cancelled: "Cancelled",
        this_month: "This Month",
        last_month: "Last Month",
        growth: "Growth",
        filter_all: "All",
        filter_pending: "Pending",
        filter_paid: "Paid",
        filter_cancelled: "Cancelled",
        history: "Commissions History",
        all: "All",
        no_commissions: "No commissions",
        no_commissions_desc: "You don't have any commissions yet. Refer users to start earning!",
        level: "Level",
        level_1: "Level 1",
        levels_2_10: "Levels 2-10",
        direct: "Direct",
        indirect: "Indirect",
        direct_referral: "Direct referral",
        indirect_referral: "Indirect referral",
        source: "Source",
        amount: "Amount",
        date: "Date",
        status: "Status",
        affiliate_program: "Affiliate Program",
        ten_levels_description: "Earn commissions on 10 levels of referrals",
        no_commissions_description: "Refer users to start earning commissions",
        go_to_affiliates: "View my affiliates",
        types: {
          AD_REVENUE: "Advertising Revenue",
          CLUB_MEMBERSHIP: "Club Membership",
          SHOP_PURCHASE: "Shop Purchase",
          CONTEST_PARTICIPATION: "Contest Participation",
          KYC_PAYMENT: "KYC Payment",
          EFM_MEMBERSHIP: "EFM Membership",
          MFM_MEMBERSHIP: "FM Joining Fees",
          FOUNDING_MEMBERSHIP_FEE: "Founding Member Fee",
          ANNUAL_MEMBERSHIP_FEE: "Annual FM Fee",
          MONTHLY_REVENUE_POOL: "Monthly Pool (5%)",
          ANNUAL_PROFIT_POOL: "Annual Pool (10%)"
        },
        rates: {
          founding_direct: "$20 per direct referral",
          founding_indirect: "$2 per indirect referral (L2-10)",
          annual_direct: "$10 per direct referral",
          annual_indirect: "$1 per indirect referral (L2-10)"
        },
        direct: "Direct",
        indirect: "Indirect",
        sort_by_date: "By date",
        sort_by_amount: "By amount",
        sort_by_type: "By type",
        filter_all: "All types",
        filter_by_type: "Filter by type",
        filter_by_status: "Filter by status"
      },
      subtitle: "Track your progress, manage your contests, and grow your network",
      quick_actions: "Quick Actions",
      recent_activity: "Recent Activity",
      no_activity: "No recent activity",
      position: {
        title: "My Position",
        no_contests: "No active contests",
        rank: "Rank",
        points: "Points",
        contests: "Beauty Contest",
        clubs: "Premium Club",
        affiliates: "Affiliates",
        status: "Status",
        members: "Members",
        referrals: "Referrals",
        commissions: "Commissions",
        active: "Active"
      },
      contests: {
        title: "Contests",
        subtitle: "Discover and participate in contests from your city and country",
        description: "Discover and participate in the most popular contests",
        no_contests: "No contests available",
        no_description: "No description available",
        all: "All",
        nomination: "Nominations",
        participations: "Participations",
        filter_level: "Level",
        level_city: "City",
        level_country: "Country",
        all_levels: "All levels",
        nomination_hint: "Nominate others to enter into competitions. Vote for contestants who have been nominated by their fans.",
        participations_hint: "Participate yourself in competitions. Contestants sign up directly to compete.",
        nominate: "Nominate",
        edit_nomination: "Edit your Nomination",
        edit_participation: "Edit your Participation",
        edit: "Edit",
        tooltip_nominate: "Click to nominate in this contest and submit your entry",
        time_remaining_to_nominate: "Time remaining to nominate",
        search_placeholder: "Search for a contest...",
        search_button: "Search",
        sort: "Sort by",
        sort_participants: "Most participants",
        sort_votes: "Most votes",
        sort_date: "Most recent",
        sort_name: "Name (A-Z)",
        filter_continent: "Continent",
        filter_country: "Country",
        all_countries: "All countries",
        search_country_placeholder: "Search for a country...",
        no_country_found: "No country found",
        continents: {
          all: "All continents",
          africa: "Africa",
          asia: "Asia",
          europe: "Europe",
          north_america: "North America",
          south_america: "South America",
          oceania: "Oceania",
          antarctica: "Antarctica"
        },
        my_continent: "My continent",
        my_country: "My country",
        voting_type: "Voting type",
        voting_level_country: "National",
        voting_level_city: "City",
        voting_level_regional: "Regional",
        voting_level_continent: "Continental",
        voting_level_global: "Global",
        status: "Status",
        level: "Level",
        city: "City",
        country: "National",
        continental: "Continental",
        regional: "Regional",
        global: "Global",
        contestants: "Contestants",
        likes: "Likes",
        comments: "Comments",
        received: "Received",
        participate: "Participate",
        be_first_to_nominate: "Be the first to nominate!",
        be_first_to_participate: "Be the first to participate!",
        empty_nomination_message: "No nominations yet. Start by nominating someone from your country!",
        empty_participation_message: "No participants yet. Be the first to participate in this contest!",
        tips: "Tips",
        tip_nomination_video: "Import video content",
        tip_nomination_video_desc: "You can import content from a user from YouTube or Vimeo from your country.",
        tip_nomination_country: "Same country required",
        tip_nomination_country_desc: "The content must come from a user from your country.",
        tip_nomination_required: "Video required",
        tip_nomination_required_desc: "Videos are required for nominations.",
        tip_nomination_platforms: "Supported platforms",
        tip_nomination_platforms_desc: "YouTube and TikTok only. YouTube Shorts, Instagram, Snapchat and Facebook are not accepted.",
        tip_participation_content: "Use your own content",
        tip_participation_content_desc: "Share your own photos and videos to participate in the contest.",
        tip_participation_media: "Required media",
        tip_participation_media_desc: "Check the image and video requirements for this contest.",
        tip_participation_verification: "Verification required",
        tip_participation_verification_desc: "Make sure your account is verified to participate.",
        tip_participation_quality: "Content quality",
        tip_participation_quality_desc: "Share your best content to maximize your chances of winning.",
        contest_type: {
          beauty: "Beauty",
          handsome: "Handsome",
          latest_hits: "Latest Hits",
          talent: "Talent",
          photography: "Photography",
          fitness: "Fitness",
          fashion: "Fashion",
          music: "Music",
          dance: "Dance",
          cooking: "Cooking",
          art: "Art",
          comics: "Comics",
          other: "Other"
        },
        men: "Men",
        women: "Women",
        add_favorite: "Add to favorites",
        remove_favorite: "Remove from favorites",
        added_to_favorites: "Added to favorites",
        removed_from_favorites: "Removed from favorites",
        open: "Open",
        open_for_candidacy: "Open for candidacy",
        closed: "Closed",
        submission_closed: "Submissions are closed for this contest.",
        submission_closed_message: "The submission deadline has passed.",
        no_active_rounds: "No active rounds accepting submissions at this time.",
        description: "Description",
        requirements: "Requirements",
        kyc_required: "Identity verification",
        kyc_required_description: "Only participants with verified identity are allowed to contest",
        visual_verification: "Photo of yourself required",
        visual_verification_description: "A photo of yourself is required to participate in this contest",
        voice_verification: "Voice verification",
        voice_verification_description: "Voice verification is required to participate in this contest",
        brand_verification: "Verified brand",
        brand_verification_description: "Only verified brands are allowed to participate in this contest",
        content_verification: "Original content required",
        content_verification_description: "Only original content is allowed to participate in this contest",
        gender_restriction: "Gender restriction",
        gender_restriction_female_description: "Only female participants are allowed to contest",
        gender_restriction_male_description: "Only male participants are allowed to contest",
        age_restriction: "Age restriction",
        age_restriction_description: "Only participants within the specified age range can participate",
        years: "years",
        contest_info: "Contest Information",
        contest_dates: "Contest Dates",
        submission_start: "Submission Start",
        submission_end: "Submission End",
        voting_start: "Voting Start",
        participant_type: "Participant Type",
        participant_individual: "Individual",
        participant_pet: "Pet",
        participant_club: "Club",
        participant_content: "Content",
        male_only: "Male Only",
        female_only: "Female Only",
        max_favorites: "5 favorites max",
        favorite_limit_reached: "Favorite limit reached",
        top_participants: "Top Participants",
        top_5_description: "The 5 best participants in the contest",
        view: "View",
        contestant: "contestant",
        view_contestants: "View contestants",
        view_all_contestants: "View all contestants",
        top_contestants: "Top Contestants",
        view_contestants_count: "contestant",
        view_contestants_empty: "No contestants",
        view_contestants_description: "Discover all contestants and vote for your favorites",
        time_remaining: "Time remaining",
        time_remaining_to_participate: "Time remaining to contest",
        time_unit_days: "d",
        time_unit_hours: "h",
        time_unit_minutes: "m",
        time_unit_seconds: "s",
        candidacy_ends: "Candidacy ends",
        participation_ongoing: "Candidacies are still open",
        vote: "Vote",
        view_details: "View Details",
        already_voted: "Already voted",
        already_voted_message: "You have already voted for this contestant.",
        cannot_vote: "You cannot vote for this contestant",
        owner_cannot_vote: "Owner, cannot vote",
        own_cannot_vote: "Own, cannot vote",
        restriction_different_city: "Different city",
        restriction_different_country: "Different country",
        restriction_different_region: "Different region",
        restriction_different_continent: "Different continent",
        restriction_own_contestant: "Your contestant",
        restriction_not_authenticated: "Login required",
        restriction_geographic: "Geographic restriction",
        restriction_user_not_found: "User not found",
        restriction_different_city_desc: "You can only vote for contestants from your city",
        restriction_different_country_desc: "You can only vote for contestants from your country",
        restriction_different_region_desc: "You can only vote for contestants from your region",
        restriction_different_continent_desc: "You can only vote for contestants from your continent",
        restriction_own_contestant_desc: "You cannot vote for your own contestant",
        restriction_not_authenticated_desc: "Please login to vote",
        restriction_geographic_desc: "You cannot vote due to geographic restrictions",
        restriction_user_not_found_desc: "User not found",
        vote_restriction: "Vote restriction",
        votes: "votes",
        shares: "Shares",
        submission: "Submission",
        voting: "Voting",
        tooltip_info: "View contest details and requirements",
        tooltip_time_remaining: "Time remaining before contesting ends",
        tooltip_gender_restriction_female: "This contest is for women only",
        tooltip_gender_restriction_male: "This contest is for men only",
        tooltip_level_city: "City-level contest",
        tooltip_level_country: "National-level contest",
        tooltip_level_regional: "Regional-level contest",
        tooltip_level_continental: "Continental-level contest",
        tooltip_level_global: "Global-level contest",
        tooltip_open: "Registrations are currently open. You can participate in this contest.",
        tooltip_contestants: "Number of participants in this contest",
        tooltip_votes: "Total number of votes received",
        tooltip_participate: "Click to contest in this contest and submit your entry",
        tooltip_view_contestants: "View all participants in this contest",
        tooltip_view_contestants_closed: "Contesting is closed. View contest participants",
        tooltip_view_contestants_cannot_participate: "You cannot contest at the moment. View contest participants",
        tooltip_closed: "Contesting is closed. Registrations are no longer accepted.",
        tooltip_voting_open: "Voting is currently open. You can vote for participants.",
        tooltip_rank: "Ranking in this contest",
        tooltip_author: "View participant profile",
        tooltip_votes_author: "Votes received. Hover to see the list of voters.",
        start: "Start",
        end: "End",
        add_to_favorites: "Add to favorites",
        remove_from_favorites: "Remove from favorites",
        reaction_added: "Reaction added",
        reaction_removed: "Reaction removed",
        no_reactions: "No reactions",
        no_votes: "No votes",
        no_favorites: "No favorites",
        more: "more",
        loading: "Loading...",
        votes: "Votes",
        favorites: "Favorites",
        points: "points",
        share: "Share",
        share_title: "Share this participant",
        share_description: "Share this participant with your friends and network",
        share_link_label: "Share link",
        copy: "Copy",
        copied: "Copied",
        share_natively: "Share natively",
        report: "Report",
        reply: "Reply",
        reply_placeholder: "Write a reply...",
        show_replies: "Show {count} reply(ies)",
        hide_replies: "Hide {count} reply(ies)",
        like_added: "Like added",
        like_removed: "Like removed",
        comment_added: "Comment added",
        reply_added: "Reply added",
        reactions: "Reactions",
        you_reacted: "You reacted",
        no_reactions: "No reactions yet",
        people_reacted: "people reacted",
        be_first_to_react: "Be the first to react",
        participant: "Participant",
        rank: "Rank",
        reaction: "Reaction",
        search_contestant: "Search for a contestant...",
        filtered_by_country: "Filtered by your country",
        no_contestants: "No participants yet",
        no_contestants_found: "No contestants found",
        like: "Like",
        love: "Love",
        wow: "Wow",
        dislike: "Dislike",
        favorite: "Favorite",
        comments_description: "Share your thoughts on this participant",
        add_comment_placeholder: "Add a comment...",
        sending: "Sending...",
        send: "Send",
        no_comments: "No comments yet",
        cancel: "Cancel",
        mention_hint: "Type @ to mention someone",
        edit: "Edit",
        delete: "Delete",
        vote_error: "Error voting. Please try again.",
        voting_not_open: "Voting is not yet open for this contest.",
        already_voted_error: "Already voted.",
        cannot_vote_own: "You cannot vote for your own entry.",
        vote_success: "Vote recorded successfully!",
        vote_replaced: "Vote replaced successfully!",
        my_votes: "My votes",
        no_votes_yet: "Vote for your favorite contestants!",
        replace_vote_title: "Replace a vote",
        replace_vote_message: "You already have 5 votes. Do you want to replace",
        replace_vote_position: "(5th position, 1 point) with this contestant?",
        replace_vote_confirm: "Replace",
        max_votes_reached: "You have reached the maximum of 5 votes",
        empty_slot: "Empty slot",
        votes_remaining: "{n} vote(s) remaining",
        drag_to_reorder: "Drag to reorder",
        vote_gender_restriction_male: "This contest is reserved for male participants. Only female participants can vote.",
        vote_gender_restriction_female: "This contest is reserved for female participants. Only male participants can vote.",
        vote_gender_not_set: "Your profile does not contain gender information. Please complete your profile to vote in this contest.",
        gender: "Gender",
        age: "Age",
        years: "years",
        country: "Country",
        city: "City",
        bio: "Biography",
        rank: "Rank",
        votes: "Votes",
        male: "Male",
        female: "Female",
        my_applications: {
          title: "My Applications",
          description: "View your applications and ranking",
          no_applications: "You don't have any applications yet",
          browse_contests: "Browse contests",
          status: "Status",
          status_pending: "Pending",
          status_approved: "Approved",
          status_rejected: "Rejected",
          rank: "Rank",
          view_details: "View Details",
          view_page: "View Page",
          edit_not_available: "Editing not available for this contest",
          delete_not_available: "Deletion not available for this contest",
          delete_confirm_message: "Are you sure you want to delete this application? This action cannot be undone.",
          details: "Details",
          statistics: "Statistics",
          total_shares: "Total shares",
          shares_by_platform: "Shares by platform",
          no_shares: "No shares yet",
          contest: "Contest",
          date: "Date",
          media: "Media",
          no_title: "No title",
          user: "User",
          media_alt: "Media",
          video_alt: "Video"
        },
        participation_form: {
          title: "Participate in Contest",
          description: "Select your best photo or video to participate in this contest",
          edit_title: "Edit a Contestant",
          edit_description: "Update your submission details",
          nominate_title: "Nominate a Contestant",
          nominate_description: "Import your video from YouTube or TikTok",
          select_media: "Select your media",
          drag_drop: "Drag and drop your file here",
          file_info: "or click to select (Images: JPG, PNG, GIF | Videos: MP4, WebM | Max: 100MB)",
          submit: "Submit my entry",
          success: "Your application has been submitted successfully. It will be reviewed by our team.",
          success_title: "✅ Application submitted successfully!",
          success_edit: "Your application has been updated successfully.",
          already_participating: "ℹ️ You already have an application for this contest. You can only submit one application per contest.",
          edit_participation: "Edit my application",
          click_add_images: "Click to add images",
          preparing: "Preparing...",
          checking_files: "Checking files...",
          uploading: "Uploading...",
          images_format: "Images",
          click_add_video: "Click to add a video",
          video_format: "Video",
          cancel: "Cancel",
          error: {
            no_media_selected: "Please select a file",
            invalid_file_type: "Unsupported file type",
            file_too_large: "File is too large (max 100MB)",
            contest_not_found: "Contest not found",
            submit_error: "Error submitting entry",
            gender_restriction_male: "This contest is reserved for male participants only.",
            gender_restriction_female: "This contest is reserved for female participants only.",
            gender_not_set: "Your profile does not contain gender information. Please complete your profile to participate in this contest.",
            already_submitted: "You already have a submission for this contest.",
            submission_closed: "Submissions are closed for this contest.",
            deadline_passed: "The submission deadline has passed."
          }
        },
        suggest_contest: {
          title: "Suggest a Contest",
          description: "Propose a contest idea to our team",
          button: "Suggest a Contest",
          name_label: "Contest Name",
          name_placeholder: "Ex: Beauty Contest 2024",
          description_label: "Description",
          description_placeholder: "Describe your contest idea...",
          category_label: "Category",
          category_placeholder: "Select a category",
          submit: "Send Suggestion",
          submitting: "Sending...",
          success: "Your suggestion has been sent successfully!",
          success_message: "Thank you for your suggestion. Our team will review it and keep you informed.",
          cancel: "Cancel",
          error: {
            name_required: "Contest name is required",
            category_required: "Category is required",
            submit_error: "Error sending suggestion",
            network_error: "Connection error. Check your internet connection.",
            server_error: "Server error. Please try again later."
          }
        },
        report_contestant: {
          title: "Report Contestant",
          description: "Describe the reason for your report. Our team will review your request.",
          contestant: "Contestant",
          reason_label: "Reason for report",
          reason_placeholder: "Select a reason",
          description_label: "Detailed description",
          description_placeholder: "Describe in detail the reason for your report (minimum 10 characters)...",
          characters: "characters",
          submit: "Submit Report",
          submitting: "Submitting...",
          success: "Your report has been sent successfully!",
          cancel: "Cancel",
          reasons: {
            spam: "Spam",
            inappropriate: "Inappropriate content",
            harassment: "Harassment",
            fake: "Fake account",
            copyright: "Copyright violation",
            other: "Other"
          },
          error: {
            reason_required: "Reason is required",
            description_required: "Description is required",
            description_min_length: "Description must contain at least 10 characters",
            submit_error: "Error sending report",
            network_error: "Connection error. Check your internet connection.",
            server_error: "Server error. Please try again later."
          }
        }
      },
      favorites: {
        title: "My Favorites",
        description: "View your favorite contests and contestants",
        description_contestants: "Organize your favorite contestants by drag and drop",
        contests_tab: "Contests",
        contestants_tab: "Contestants",
        no_favorite_contests: "You don't have any favorite contests yet",
        no_favorite_contestants: "You don't have any favorite contestants yet",
        no_favorites_yet: "No favorites yet",
        no_favorites_hint: "Add contestants to your favorites from a contest page by clicking the star.",
        browse_contests: "Browse contests"
      },
      myhigh5: {
        title: "MyHigh5",
        description: "The 5 contestants you have voted for",
        hint: "Your first vote is displayed in position 1, and your most recent vote in position 5. You can vote for a maximum of 5 contestants.",
        no_votes: "No votes yet",
        no_votes_description: "You haven't voted for any contestants yet. Explore contests to vote!",
        explore_contests: "Explore contests",
        explore_more: "Explore more contests",
        remaining_votes: "You can still vote for {count} more contestant(s)",
        votes_label: "votes",
        hint_dnd: "Drag and drop to reorder your votes. 1st place gets 5 points, 2nd gets 4 points, 3rd gets 3 points, 4th gets 2 points, and 5th gets 1 point. You may vote for as many contestants as you wish, but only the top 5 are counted for voting credit. Any additional vote after the fifth will replace the contestant currently in 5th place.",
        hint_tap:
          "Tap a contestant’s profile photo to select them, then tap another photo to move them to that rank. Tap the same photo again to cancel.",
        tap_reorder_second: "Tap another contestant’s photo to move {name} to that position.",
        tap_reorder: "Tap to select, then tap another photo to reorder",
        drag_reorder: "Drag profile photo to reorder your High5",
        rank: "Rank",
        points: "Points",
        contestant: "Contestant",
        location: "Location",
        total_votes: "Total votes",
        vote_date: "Vote date",
        order_saved: "Order saved!",
        order_error: "Error saving order",
        points_legend: "Points system",
        points_label: "points",
        active_tab: "Active",
        history_tab: "History",
        no_history: "No history",
        no_history_description: "You don't have any vote history yet.",
        inactive: "Ended"
      },
      leaderboard: {
        title: "Sponsors Leaderboard",
        subtitle: "Top 10 sponsors with the most verified direct referrals",
        mfm_subtitle: "Top 10 MFM sponsors with the most direct referrals who are MFM",
        regular_tab: "General Leaderboard",
        mfm_tab: "MFM Leaderboard",
        referrals: "Referrals",
        benefit: "Benefit",
        champion: "Champion",
        no_data: "No sponsors found",
        info_title: "How does the leaderboard work?",
        info_description: "The leaderboard is based on the number of direct referrals (level 1) who are MFMs. The more direct referred MFMs you have, the higher your position in the leaderboard.."
      }
    },
    kyc: {
      verification_required: "Identity Verification Required",
      verification_required_description: "To participate in contests and withdraw your winnings, you must verify your identity.",
      start_verification: "Start Verification",
      already_verified: "Identity Verified",
      already_verified_description: "Your identity has been successfully verified. You can now enjoy all features.",
      verification_in_progress: "Verification In Progress",
      verification_in_progress_description: "Your verification request is being processed. We will notify you once the process is complete.",
      verification_continue_description: "You have a verification in progress. You can continue it or refresh the status.",
      continue_verification: "Continue Verification",
      login_required: "Please log in to continue",
      init_error: "Unable to start verification",
      max_attempts_reached: "Maximum attempts reached",
      max_attempts_description: "You have used all your verification attempts. Please contact our support for assistance.",
      max_attempts_can_pay: "You have used your free attempts. You can purchase additional attempts to continue.",
      buy_attempts: "Purchase additional attempts",
      price_per_attempt: "Price per attempt",
      pay_and_retry: "Pay and retry",
      attempts_remaining: "Attempts remaining",
      attempts_used: "Attempts used",
      verification_status: "Verification Status",
      verification_status_description: "Check the status of your identity verification",
      verification_rejected: "Verification Rejected",
      verification_rejected_description: "Your verification request was rejected. You can submit a new request.",
      rejection_reason: "Rejection Reason",
      submitted_on: "Submitted on",
      submit_again: "Try Again",
      verification_steps: "How does it work?",
      step_1_title: "1. Personal Information",
      step_1_desc: "Provide your basic personal information",
      step_2_title: "2. Identity Document",
      step_2_desc: "Take a photo of your ID document",
      step_3_title: "3. Verification Selfie",
      step_3_desc: "Take a selfie to confirm your identity",
      accepted_documents: "Accepted Documents",
      doc_passport: "Passport",
      doc_id_card: "ID Card",
      doc_driving_license: "Driving License",
      initiating: "Starting...",
      redirect_notice: "You will be redirected to our secure verification partner",
      follow_instructions: "Follow the instructions below to complete your identity verification.",
      secure_verification: "Secure verification by our certified partner",
      uploaded_documents: "Uploaded Documents",
      document_front: "Document Front",
      document_back: "Document Back",
      selfie: "Selfie",
      steps: "Verification Steps",
      personal_info: "Personal Information",
      personal_info_desc: "Enter your personal details",
      document_info: "Document Information",
      document_info_desc: "Provide your document details",
      review_submit: "Review & Submit",
      review_submit_desc: "Review and submit your information",
      secure: "Your Data is Secure",
      secure_desc: "All your information is encrypted and protected according to international standards.",
      first_name: "First Name",
      first_name_placeholder: "Enter your first name",
      last_name: "Last Name",
      last_name_placeholder: "Enter your last name",
      date_of_birth: "Date of Birth",
      nationality: "Nationality",
      nationality_placeholder: "Enter your nationality",
      address: "Address",
      address_placeholder: "Enter your full address",
      document_type: "Document Type",
      passport: "Passport",
      national_id: "National ID",
      drivers_license: "Driver's License",
      document_number: "Document Number",
      document_number_placeholder: "Enter your document number",
      issuing_country: "Issuing Country",
      issuing_country_placeholder: "Enter the country that issued your document",
      document_upload_next: "Document Upload Coming Next",
      document_upload_next_desc: "In the next step, you'll upload photos of your document (front and back) and a selfie.",
      processing_time: "Processing Time",
      processing_time_desc: "Your verification will be processed within 24-48 hours. You'll receive an email notification once completed.",
      submission_success: "Verification submitted successfully! Redirecting...",
      submit_verification: "Submit Verification",
      errors: {
        first_name_required: "First name is required",
        last_name_required: "Last name is required",
        date_of_birth_required: "Date of birth is required",
        nationality_required: "Nationality is required",
        address_required: "Address is required",
        document_type_required: "Document type is required",
        document_number_required: "Document number is required",
        issuing_country_required: "Issuing country is required",
        document_front_required: "Document front photo is required",
        document_back_required: "Document back photo is required",
        selfie_required: "Selfie is required"
      }
    },
    payment: {
      payment_required: "Payment Required",
      payment_instructions: "Payment Instructions",
      payment_description: "To access {product}, please make a payment of {amount}.",
      send_exact_amount: "Send exactly {amount} to the address below.",
      kyc_verification: "KYC Verification",
      efm_membership: "EFM Membership",
      kyc_description: "Identity verification to participate in contests",
      efm_description: "Become an EFM founding member",
      validity_one_year: "Validity: 1 year per unit",
      unit: "unit",
      quantity: "Quantity",
      total: "Total",
      choose_method: "Choose your payment method",
      choose_product: "Choose a product",
      choose_product_description: "Select the product you want to purchase.",
      payment_method: "Payment method",
      cryptocurrencies: "Cryptocurrencies",
      other_methods: "Other methods",
      card: "Bank card",
      bank_transfer: "Bank transfer",
      network: "Network",
      amount_to_send: "Amount to send",
      receiving_address: "Receiving address",
      bank_details: "Bank details",
      beneficiary: "Beneficiary",
      bank_reference_info: "Include your email as the transfer reference for easier identification.",
      network_warning: "Make sure to send the exact amount on the correct network. Network errors can result in loss of funds.",
      payment_done: "I have made the payment",
      validation_time_info: "After your payment, validation may take a few minutes to a few hours depending on the method chosen.",
      min: "Min",
      min_amount: "Minimum amount",
      min_amount_error: "The minimum amount is {amount}",
      enter_amount: "Enter the amount",
      custom_amount: "Custom amount",
      card_coming_soon: "Card payment coming soon",
      creating_payment: "Creating payment...",
      order_id: "Reference",
      add_recipients: "Add recipients",
      recipients_description: "Add users you want to pay for",
      method_description: "Choose your payment method",
      instructions_description: "complete payment within your wallet",
      recipient: "Recipient",
      username_or_email: "Username or email",
      user_not_found: "User not found",
      product_type: "Product type",
      amount: "Amount",
      min_100: "Minimum 100 USD",
      add_recipient: "Add a recipient",
      recipients_count: "recipient(s)",
      confirm_close_title: "Close payment?",
      confirm_close_description: "Your progress will be lost. Are you sure you want to close?",
      pay_for_myself: "Pay for myself",
      pay_for_others: "Pay for others",
      add_other_user: "Add another user",
      checking: "Checking...",
      waiting_confirmation: "Payment awaiting confirmation...",
      not_received: "Payment not received yet. Please try again.",
      success_title: "Payment confirmed!",
      success_description: "Your payment has been received and confirmed. You can now continue.",
      amount_paid: "Amount paid",
      auto_checking: "Auto-verification active",
      last_check: "Last check",
      waiting_payment: "Waiting for payment...",
      confirming: "Payment detected, confirming...",
      partially_paid: "Partial payment received. Please complete the amount.",
      kyc_verification: "KYC Service",
      mfm_membership: "MFM",
      annual_membership: "Annual Membership",
      buy_services: "Buy Services",
      select_for_myself: "For myself",
      select_service: "Select a service for yourself",
      kyc_description: "Identity verification to participate in contests",
      mfm_description: "Access to monthly (5%) and annual (10%) revenue pools + random referrals",
      annual_description: "Annual renewal of Founding Member status",
      total_to_pay: "Total to pay",
      card: "Credit card",
      bank_transfer: "Bank transfer",
      no_payment_id: "No payment ID found",
      payment_expired: "This payment has expired. Please create a new payment.",
      fetch_error: "Error loading payment details"
    },
    contests: {
      profile_incomplete_title: "Incomplete Profile",
      profile_incomplete_message: "Complete your profile to participate in contests.",
      complete_profile: "Complete",
      kyc_required_title: "Identity Verification Required",
      kyc_required_message: "Verify your identity (KYC) to participate in contests.",
      kyc_recommended_title: "Identity Verification Recommended",
      kyc_recommended_message: "Some contests require KYC verification to participate.",
      verify_identity: "Verify"
    },
    user: {
      profile: "Profile",
      settings: "Settings",
      kyc: "KYC Verification",
      subscription: "Subscription",
      logout: "Logout"
    },
    notifications: {
      title: "Notifications",
      no_notifications: "No notifications",
      mark_all_read: "Mark all as read",
      mark_as_read: "Mark as read",
      view_all: "View all notifications",
      types: {
        system: "System",
        contest: "Contest",
        compte: "Account"
      },
      messages: {
        new_vote: "voted for your application",
        new_comment: "commented on your application",
        new_reply: "replied to your comment",
        new_like: "liked your comment",
        new_reaction: "reacted to your application"
      },
      time: {
        just_now: "Just now",
        seconds_ago: "seconds ago",
        minute_ago: "minute ago",
        minutes_ago: "minutes ago",
        hour_ago: "hour ago",
        hours_ago: "hours ago",
        day_ago: "day ago",
        days_ago: "days ago",
        week_ago: "week ago",
        weeks_ago: "weeks ago",
        month_ago: "month ago",
        months_ago: "months ago",
        year_ago: "year ago",
        years_ago: "years ago"
      }
    },
    pages: {
      contests: {
        badge: "Ongoing contests",
        title: "Discover Our Contests",
        subtitle: "Participate, nominate, or vote in exciting competitions that progress from the local level to the global level.",
        search_placeholder: "Search a contest...",
        filters: {
          all: "All",
          city: "City",
          country: "Country",
          regional: "Regional",
          continental: "Continental",
          global: "Global"
        },
        stats: {
          active: "Active contests",
          participants: "Participants",
          levels: "Levels"
        },
        all_contests: "All contests",
        contests_filter: "Contests",
        results: "result",
        reset_filters: "Reset filters",
        join_community: "Join the community",
        learn_more: "Learn more",
        no_results: "No contest found",
        try_different_filter: "Try another filter or search term",
        auth_required_title: "Login Required",
        auth_required_description: "You must be logged in to participate in contests or view contestants.",
        auth_required_benefits_title: "By logging in, you will be able to:",
        auth_required_benefit_participate: "Participate in contests",
        auth_required_benefit_view_contestants: "View contestants",
        auth_required_benefit_vote: "Vote for your favorites",
        auth_required_benefit_comment: "Comment and interact",
        auth_required_login: "Sign In",
        auth_required_register: "Create an account",
        cta: {
          title: "Ready to participate?",
          subtitle: "Create your free account and start competing today!",
          button: "Create my account"
        }
      },
      clubs: {
        title: "Exclusive Fan Clubs",
        subtitle: "Join passionate communities and access exclusive content",
        search_placeholder: "Search a club...",
        features: {
          dsp: "DSP Payment",
          multi_admin: "Multi-Admin",
          affiliate: "Affiliate Program"
        },
        no_results: "No club found",
        try_different_filter: "Try another filter",
        cta: {
          title: "Create your own Club",
          subtitle: "Monetize your content, manage your community and earn through the affiliate program.",
          feature1: "Get paid your specified subscription fee, minus transaction costs",
          feature2: "Multi-administrator management",
          feature3: "Affiliate commissions are paid to members from 20% of the website margin added on top of your specified subscription fee, distributed up to 10 generations deep.",
          button: "Create my Club"
        }
      },
      about: {
        title: "About MyHigh5",
        subtitle: "The first holistic online contest platform that discovers and showcases talent from the city level to the global stage.",
        mission: {
          title: "Our Mission",
          description: "Democratize access to contests and allow every talent to shine on the world stage."
        },
        values: {
          title: "Our Values",
          subtitle: "The principles that guide each of our decisions"
        },
        timeline: {
          title: "Our Journey"
        },
        team: {
          title: "Our Team",
          subtitle: "Passionate people dedicated to your success"
        },
        cta: {
          title: "Join the MyHigh5 Adventure",
          subtitle: "Be part of a global community of talents.",
          button: "Start Now"
        }
      },
      contact: {
        title: "Contact Us",
        subtitle: "Our team is here to help. We usually respond within 24 hours.",
        form: {
          title: "Send us a message",
          name: "Full name",
          email: "Email",
          category: "Category",
          subject: "Subject",
          message: "Message",
          submit: "Send message"
        },
        faq: {
          title: "Frequently Asked Questions"
        },
        hours: {
          title: "Support hours"
        },
        categories: {
          title: "How can we help you?"
        }
      }
    },
    verification: {
      requirements_title: "Required Verifications",
      requirements_description: "This contest requires the following verifications to participate.",
      contest: "Contest",
      progress: "Progress",
      completed: "Completed",
      required: "Required",
      verify: "Verify",
      proceed: "Continue",
      incomplete_warning: "Complete all verifications to participate.",
      kyc_verification: "KYC Verification",
      visual_verification: "Visual Verification (Selfie)",
      voice_verification: "Voice Verification",
      selfie: "Verification Selfie",
      selfie_with_pet: "Selfie with your pet",
      selfie_with_document: "Selfie with document",
      selfie_instructions: "Take a clear photo of your face, well lit.",
      selfie_pet_instructions: "Take a clear photo of yourself with your pet.",
      selfie_document_instructions: "Take a photo of yourself with a visible ID.",
      voice_instructions: "Record your voice for a few seconds.",
      use_camera: "Use camera",
      upload_image: "Upload image",
      camera_error: "Unable to access camera",
      microphone_error: "Unable to access microphone",
      file_too_large: "File is too large",
      file_too_large_with_size: "File is too large. Maximum size allowed",
      invalid_file_type: "Invalid file type",
      upload_error: "Upload error",
      capture: "Capture",
      retake: "Retake",
      confirm: "Confirm",
      tap_to_record: "Tap to record",
      recording: "Recording...",
      recording_complete: "Recording complete",
      play: "Play",
      stop: "Stop",
      selfie_success: "Selfie saved successfully",
      voice_success: "Voice recording saved successfully"
    }
  },
  es: {
    not_found: {
      title: "Página no encontrada",
      description: "Lo sentimos, la página que buscas no existe o ha sido movida.",
      go_back: "Volver",
      go_home: "Inicio",
      quick_links: "Enlaces rápidos",
      help_text: "Si crees que esto es un error, por favor contacta con nuestro soporte."
    },
    admin: {
      title: "Panel de Administración",
      subtitle: "Gestiona tu plataforma",
      nav: {
        main: "Principal",
        dashboard: "Panel de control",
        management: "Gestión",
        seasons: "Temporadas",
        contests: "Concursos",
        contestants: "Participantes",
        users: "Usuarios",
        kyc: "KYC",
        reports: "Informes",
        configuration: "Configuración",
        categories: "Categorías",
        commission_settings: "Configuración de comisiones",
        suggested_contests: "Concursos sugeridos",
        transactions: "Transacciones",
        microservices: "Microservicios"
      },
      dashboard: {
        total_seasons: "Total de temporadas",
        active: "activos",
        inactive: "inactivos",
        admins: "administradores",
        votes: "Votos",
        total_votes: "Total de votos",
        comments: "Comentarios",
        total_comments: "Total de comentarios",
        quick_actions: "Acciones rápidas",
        user_progress: "Progresión de usuarios",
        reports: {
          title: "Informes",
          description: "Genera y consulta tus informes",
          financial_report: "Informe financiero",
          financial_description: "Ingresos, gastos y beneficios",
          users_report: "Informe de usuarios",
          users_description: "Estadísticas y progresión",
          contests_report: "Informe de concursos",
          contests_description: "Rendimiento de concursos",
          votes_report: "Informe de votos",
          votes_description: "Análisis de votos",
          recent_reports: "Informes recientes"
        },
        chart_labels: {
          total_users: "Total de usuarios",
          active_users: "Usuarios activos",
          new_users: "Nuevos usuarios"
        },
        periods: {
          today: "Hoy",
          yesterday: "Ayer",
          week: "Semana",
          month: "Mes",
          year: "Año"
        },
        statistics: {
          total_deposits: "Total Depósitos",
          total_withdrawals: "Total Retiros",
          verified_users: "Usuarios Verificados",
          reports: "Informes",
          categories: "Categorías",
          deposits_chart: "Gráfico de Depósitos",
          withdrawals_chart: "Gráfico de Retiros",
          categories_chart: "Estadísticas de Categorías",
          reports_by_type: "Informes por Tipo",
          amount_eur: "Cantidad ($)",
          deposits_count: "depósitos",
          withdrawals_count: "retiros",
          kyc_verified: "KYC verificado",
          reports_count: "Informes",
          categories_total: "Total",
          amount: "Cantidad",
          count: "Cantidad",
          contests: "Concursos",
          uses: "Usos",
          period: "Período:",
          custom: "Personalizado",
          apply: "Aplicar",
          loading: "Cargando...",
          refresh: "Actualizar",
          no_data_available: "No hay datos disponibles"
        }
      },
      profile: {
        participations: "Participaciones",
        total_votes: "Votos",
        total_favorites: "Favoritos",
        followers: "Seguidores",
        following: "Siguiendo",
        contestants: "Participaciones",
        all_rounds: "Todos",
        no_entries: "Sin participaciones por el momento",
        verified: "Verificado",
        years: "años",
        follow: "Seguir",
        unfollow: "Dejar de seguir",
        followed: "Ahora sigues a este usuario",
        unfollowed: "Dejaste de seguir a este usuario"
      },
      seasons: {
        title: "Gestionar Temporadas",
        description: "Crear, editar y gestionar temporadas de concursos",
        new_season: "Nueva Temporada",
        edit_season: "Editar Temporada",
        create_season: "Crear Temporada",
        year: "Año",
        season_number: "Número de Temporada",
        season_title: "Título",
        status: "Estado",
        start_date: "Fecha de Inicio",
        end_date: "Fecha de Fin",
        upload_end_date: "Fin de Carga",
        upcoming: "Próxima",
        upload_phase: "Fase de Carga",
        voting_active: "Votación Activa",
        voting_ended: "Votación Finalizada",
        completed: "Completada",
        cancelled: "Cancelada",
        edit: "Editar",
        delete: "Eliminar",
        cancel: "Cancelar",
        create: "Crear",
        confirm_delete: "¿Estás seguro de que deseas eliminar esta temporada?",
        confirm_delete_title: "Eliminar Temporada",
        confirm_delete_message: "¿Estás seguro de que deseas eliminar esta temporada? Esta acción es irreversible.",
        no_seasons: "No se encontraron temporadas. Crea tu primera temporada.",
        create_success: "Temporada creada exitosamente",
        update_success: "Temporada actualizada exitosamente",
        delete_success: "Temporada eliminada exitosamente",
        load_error: "Error al cargar las temporadas",
        save_error: "Error al guardar",
        delete_error: "Error al eliminar",
        level: "Nivel",
        level_city: "Ciudad",
        level_country: "País",
          filter_level: "Nivel",
        level_regional: "Regional",
        level_continent: "Continente",
        level_global: "Global",
        level_placeholder: "Seleccionar un nivel",
        season_title_placeholder: "Ej: Temporada Primavera 2024",
        error_level_exists: "Ya existe una temporada con el nivel '{level}'. Solo puede haber una temporada activa por nivel.",
        error_invalid_level: "Nivel inválido. Los niveles válidos son: {levels}",
        contestants_count: "candidatos",
        contests_count: "concursos"
      },
      contests: {
        title: "Gestionar Concursos",
        description: "Crear, editar y gestionar concursos",
        new_contest: "Nuevo Concurso",
        edit_contest: "Editar Concurso",
        create_contest: "Crear Concurso",
        name: "Nombre del Concurso",
        contest_description: "Descripción",
        contest_type: "Tipo de Concurso",
        level: "Nivel",
        city: "Ciudad",
        country: "País",
        region: "Región",
        continent: "Continente",
        global: "Global",
        active: "Activo",
        inactive: "Inactivo",
        upload_open: "Carga Abierta",
        voting_active: "Votación Activa",
        edit: "Editar",
        delete: "Eliminar",
        cancel: "Cancelar",
        confirm_delete: "¿Estás seguro de que deseas eliminar este concurso?",
        image: "Imagen del Concurso",
        no_contests: "No se encontraron concursos",
        voting_restriction: "Restricción de Votación",
        none: "Ninguna",
        male_only: "Solo Hombres",
        female_only: "Solo Mujeres",
        geographic: "Geográfica",
        age_restricted: "Restricción de Edad",
        start_date: "Fecha de Inicio",
        end_date: "Fecha de Fin",
        search_placeholder: "Buscar",
        sort: "Ordenar por",
        create_success: "Concurso creado exitosamente",
        create_error: "Error al crear concurso",
        update_success: "Concurso actualizado exitosamente",
        update_error: "Error al actualizar concurso",
        delete_success: "Concurso eliminado exitosamente",
        delete_error: "Error al eliminar concurso",
        sort_date: "Fecha (Reciente)",
        sort_name: "Nombre (A-Z)",
        sort_status: "Estado",
        participant_count: "Número de Participantes",
        all_loaded: "Todos los concursos mostrados",
        creating: "Creando...",
        updating: "Actualizando...",
        candidates: "Participantes",
        confirm_delete_title: "Eliminar Concurso",
        confirm_delete_message: "¿Estás seguro de que deseas eliminar este concurso? Esta acción es irreversible.",
        submission_start: "Inicio de Envíos",
        submission_end: "Fin de Envíos",
        voting_start: "Inicio de Votación",
        voting_end: "Fin de Votación",
        contest_dates: "Fechas del Concurso",
        approved: "Aprobado",
        rejected: "Rechazado",
        filter: "Filtrar",
        approve: "Aprobar",
        reject: "Rechazar",
        view: "Ver",
        no_kyc: "Sin verificación KYC",
        verification_score: "Puntuación de Confianza",
        identity: "Identidad",
        document: "Documento",
        address: "Dirección",
        face: "Cara",
        confidence_score: "Puntuación",
        rejection_reason: "Razón del Rechazo",
        // Verification form labels
        participant_type: "Tipo de participante",
        verification_type: "Tipo de verificación",
        min_age: "Edad mínima",
        max_age: "Edad máxima",
        requires_kyc: "KYC obligatorio",
        requires_visual: "Verif. visual",
        requires_voice: "Verif. vocal",
        requires_brand: "Verif. marca",
        requires_content: "Verif. propiedad del contenido",
        // List stats
        participants: "Participantes",
        pending: "Pendiente",
        // Media requirements
        media_requirements: "Requisitos de Medios",
        requires_video: "Video obligatorio",
        max_videos: "Videos máx",
        video_duration: "Duración máx (min)",
        min_images: "Imágenes mín",
        max_images: "Imágenes máx",
        // List translations
        level_city: "Ciudad",
        level_country: "País",
        level_region: "Región",
        level_continent: "Continente",
        level_global: "Global",
        contests_count: "concursos",
        active_count: "activos",
        result: "resultado",
        results: "resultados",
        found: "encontrado(s)",
        no_results_for: "Sin resultados para",
        current_image: "Imagen actual",
        participant_individual: "Individual",
        participant_pet: "Mascota",
        participant_club: "Club",
        participant_content: "Contenido",
        kyc_required: "KYC requerido",
        kyc_not_required: "Sin KYC",
        verification_visual: "Visual",
        verification_voice: "Voz",
        verification_brand: "Marca",
        verification_content: "Contenido",
        age_restricted: "Restricción de edad",
        years: "años",
        // Form placeholders
        name_placeholder: "Ej: Concurso de belleza 2024",
        description_placeholder: "Descripción del concurso",
        type_placeholder: "Ej: beauty, handsome",
        // Auto dates
        auto_dates_title: "Fechas automáticas",
        auto_dates_description: "Las fechas se generan automáticamente",
        auto_date_upload_start: "Inicio de subidas: fecha de creación",
        auto_date_upload_end: "Fin de subidas: 1 mes después del inicio",
        auto_date_vote_start: "Inicio de votación: 1 día después del fin de subidas",
        auto_date_vote_end: "Fin de votación: 1 mes después del inicio de votación",
        // Additional form labels
        verification_requirements: "Requisitos de verificación",
        verification_none: "Ninguna",
        none: "Ninguna",
        male_only: "Solo hombres",
        female_only: "Solo mujeres",
        geographic: "Geográfico",
        // Additional placeholders
        min_age_placeholder: "Ej: 18",
        max_age_placeholder: "Ej: 35",
        search_input_placeholder: "Nombre, tipo, descripción...",
        sort: "Ordenar por",
        // Season dates
        season_dates: "Fechas de Temporadas",
        season_dates_description_edit: "Estas fechas se calculan automáticamente a partir de la fecha de inicio de votación. Puede modificarlas manualmente si es necesario.",
        season_dates_description_create: "Estas fechas se calcularán automáticamente a partir de la fecha de inicio de votación al crear. Puede prellenarlas si es necesario.",
        city_season: "Temporada Ciudad",
        country_season: "Temporada País",
        regional_season: "Temporada Regional",
        continental_season: "Temporada Continental",
        global_season: "Temporada Global",
        start_date: "Fecha de Inicio",
        end_date: "Fecha de Fin",
        // Voting type translations
        voting_type: "Tipo de Votación",
        select_voting_type: "Seleccionar un tipo de votación",
        new_voting_type: "Nuevo tipo de votación",
        voting_types_load_error: "Error al cargar tipos de votación",
        voting_type_created: "Tipo de votación creado exitosamente",
        voting_type_create_error: "Error al crear tipo de votación",
        create_voting_type: "Crear un tipo de votación",
        voting_type_name_placeholder: "Ej: Voto Ciudad - Comisión Publicidad",
        voting_level: "Nivel de votación",
        commission_source: "Fuente de comisión",
        commission_rules: "Reglas de comisión (JSON)",
        commission_rules_help: "Las reglas de comisión son opcionales. Formato: L1 para nivel 1, L2-10 para niveles 2 a 10.",
        commission_advert: "Publicidad",
        commission_affiliate: "Afiliación",
        commission_kyc: "KYC",
        commission_mfm: "MFM",
        create: "Crear",
        // Category translations
        category: "Categoría",
        select_category: "Seleccionar una categoría",
        no_category: "Sin categoría",
        add_category: "Agregar categoría",
        create_category: "Crear categoría",
        category_name_required: "El nombre de la categoría es requerido",
        category_created: "Categoría creada exitosamente",
        category_create_error: "Error al crear categoría",
        categories_load_error: "Error al cargar categorías",
        category_name_placeholder: "Ej: Pop, Rock, Hip hop",
        slug: "Slug",
        slug_placeholder: "Ej: pop, rock, hip-hop",
        slug_help: "El slug se genera automáticamente a partir del nombre. Puede modificarlo si es necesario.",
        category_description_placeholder: "Descripción de la categoría (opcional)",
        contest_type_auto_filled: "El tipo de concurso se llena automáticamente a partir de la categoría"
      },
      contestants: {
        title: "Gestionar Participantes",
        description: "Aprobar o rechazar solicitudes",
        search_placeholder: "Buscar por nombre o título...",
        all: "Todos",
        pending: "Pendiente",
        verified: "Verificado",
        filter: "Filtrar",
        approve: "Aprobar",
        reject: "Rechazar",
        view: "Ver",
        author: "Autor",
        images: "Imágenes",
        videos: "Videos",
        votes: "Votos",
        comments: "Comentarios",
        status: "Estado",
        registration_date: "Fecha de Registro",
        actions: "Acciones",
        contestant_details: "Detalles del Participante",
        close: "Cerrar",
        no_contestants: "No se encontraron participantes",
        status_pending: "Pendiente",
        status_verified: "Verificado",
        status_rejected: "Rechazado",
        approve_success: "Participante aprobado exitosamente",
        approve_error: "Error al aprobar participante",
        reject_success: "Participante rechazado exitosamente",
        reject_error: "Error al rechazar participante",
        status_update_success: "Estado del participante actualizado exitosamente",
        status_update_error: "Error al actualizar estado del participante",
        comment_delete_success: "Comentario eliminado exitosamente",
        comment_delete_error: "Error al eliminar comentario",
        comment_hide_success: "Comentario ocultado exitosamente",
        comment_hide_error: "Error al ocultar comentario",
        comment_show_success: "Comentario mostrado exitosamente",
        comment_show_error: "Error al mostrar comentario",
        comment_restore_success: "Comentario restaurado exitosamente",
        comment_restore_error: "Error al restaurar comentario",
        new_contestant: "Nuevo Participante",
        edit_contestant: "Editar Participante",
        user: "Usuario",
        select_user: "Seleccionar un usuario",
        select_season: "Seleccionar una temporada",
        no_seasons_for_level: "No hay temporadas disponibles para este nivel",
        title_placeholder: "Título del participante",
        description_placeholder: "Descripción del participante",
        create_success: "Participante creado exitosamente",
        update_success: "Participante actualizado exitosamente",
        save_error: "Error al guardar",
        seasons_load_error: "Error al cargar las temporadas",
        no_seasons_available: "No hay temporadas disponibles. Por favor, cree una temporada primero."
      },
      categories: {
        title: "Gestión de Categorías",
        description: "Cree y gestione las categorías de concursos",
        add_category: "Agregar categoría",
        search_placeholder: "Buscar una categoría...",
        no_categories: "No hay categorías todavía",
        no_categories_found: "No se encontraron categorías",
        created_at: "Creado el",
        edit_category: "Editar categoría",
        create_category: "Crear una nueva categoría",
        edit_category_description: "Edite la información de la categoría",
        create_category_description: "Complete la información para crear una nueva categoría",
        category_name: "Nombre",
        category_name_required: "El nombre es obligatorio",
        category_name_max_length: "El nombre no puede exceder 100 caracteres",
        slug: "Slug",
        slug_required: "El slug es obligatorio",
        slug_max_length: "El slug no puede exceder 100 caracteres",
        slug_invalid: "El slug solo puede contener letras minúsculas, números y guiones",
        slug_auto_generated: "El slug se genera automáticamente a partir del nombre",
        description_label: "Descripción",
        description_placeholder: "Descripción de la categoría (opcional)",
        is_active: "Categoría activa",
        cancel: "Cancelar",
        save: "Guardar",
        saving: "Guardando...",
        edit: "Editar",
        create: "Crear",
        delete: "Eliminar",
        delete_confirm: "¿Está seguro de que desea eliminar la categoría",
        category_created: "Categoría creada con éxito",
        category_updated: "Categoría actualizada con éxito",
        category_deleted: "Categoría eliminada con éxito",
        category_create_error: "Error al crear la categoría",
        category_update_error: "Error al actualizar la categoría",
        category_delete_error: "Error al eliminar la categoría",
        categories_load_error: "Error al cargar las categorías"
      },
      kyc: {
        title: "Gestionar KYC",
        description: "Aprobar o rechazar verificaciones de identidad",
        search_placeholder: "Buscar por correo o nombre...",
        pending: "Pendiente",
        approved: "Aprobado",
        rejected: "Rechazado",
        filter: "Filtrar",
        approve: "Aprobar",
        reject: "Rechazar",
        view: "Detalles",
        no_kyc: "No se encontraron verificaciones KYC",
        verification_score: "Puntuación de Confianza",
        identity: "Identidad",
        document: "Documento",
        address: "Dirección",
        face: "Cara",
        confidence_score: "Puntuación",
        rejection_reason: "Razón del Rechazo"
      },
      reports: {
        title: "Gestión de Reportes",
        description: "Gestione los reportes de contenido",
        search_placeholder: "Buscar un reporte...",
        all: "Todos",
        pending: "Pendiente",
        reviewed: "Revisado",
        resolved: "Resuelto",
        no_reports: "No hay reportes todavía",
        no_reports_found: "No se encontraron reportes",
        report_number: "Reporte #",
        reason: "Razón",
        description_label: "Descripción",
        status: "Estado",
        details: "Detalles",
        reported_contestant: "Participante Reportado",
        contestant_author: "Autor del Participante",
        reporter: "Reportador",
        contest: "Concurso",
        created_at: "Creado el",
        reviewed_at: "Revisado el",
        moderator_notes: "Notas del Moderador",
        verification_status: "Estado de Verificación",
        verification_status_pending: "Pendiente",
        verification_status_approved: "Aprobado",
        verification_status_rejected: "Rechazado",
        reason_spam: "Spam",
        reason_inappropriate: "Contenido inapropiado",
        reason_harassment: "Acoso",
        reason_fake: "Cuenta falsa",
        reason_copyright: "Violación de derechos de autor",
        reason_other: "Otro",
        no_title: "Sin título",
        load_error: "Error al cargar los reportes",
        report_details: "Detalles del Reporte",
        report_details_description: "Información completa sobre el reporte",
        reason_label: "Razón del Reporte"
      },
      suggested_contests: {
        title: "Concursos Sugeridos",
        description: "Gestione las sugerencias de concursos enviadas por los usuarios",
        search_placeholder: "Buscar una sugerencia...",
        all: "Todos",
        pending: "Pendiente",
        approved: "Aprobados",
        rejected: "Rechazados",
        no_suggestions: "No hay sugerencias todavía",
        no_suggestions_found: "No se encontraron sugerencias",
        author: "Autor",
        author_not_available: "Autor no disponible",
        unknown_date: "Fecha desconocida",
        details: "Detalles",
        contest_suggestion_details: "Detalles de la sugerencia de concurso",
        status: "Estado",
        category: "Categoría",
        description: "Descripción",
        verified: "Verificado",
        dates: "Fechas",
        created_at: "Creado el",
        updated_at: "Modificado el",
        load_error: "Error al cargar las sugerencias"
      },
      transactions: {
        title: "Gestión de Transacciones",
        description: "Consulte todas las transacciones (depósitos, retiros, etc.)",
        search_placeholder: "Buscar por referencia, descripción, usuario...",
        all_types: "Todos los tipos",
        all_statuses: "Todos los estados",
        no_transactions: "No hay transacciones todavía",
        no_transactions_found: "No se encontraron transacciones",
        transaction: "Transacción",
        transaction_details: "Detalles de la Transacción",
        transaction_details_description: "Información completa sobre la transacción",
        type: {
          deposit: "Depósito",
          withdrawal: "Retiro",
          entry_fee: "Tarifa de Entrada",
          prize_payout: "Pago de Premio",
          commission: "Comisión",
          refund: "Reembolso"
        },
        status: {
          pending: "Pendiente",
          completed: "Completado",
          failed: "Fallido",
          cancelled: "Cancelado"
        },
        user: "Usuario",
        contest: "Concurso",
        payment_method: "Método de Pago",
        product_type: "Tipo de Producto",
        amount: "Monto",
        currency: "Moneda",
        description: "Descripción",
        reference: "Referencia",
        order_id: "ID de Pedido",
        external_payment_id: "ID de Pago Externo",
        tx_hash: "Hash de Transacción",
        created_at: "Creado el",
        processed_at: "Procesado el",
        validated_at: "Validado el",
        type_label: "Tipo",
        status_label: "Estado",
        details: "Detalles",
        search: "Buscar",
        load_error: "Error al cargar las transacciones"
      },
      users: {
        title: "Gestionar Usuarios",
        description: "Gestiona roles y permisos de usuarios",
        search_placeholder: "Buscar por correo, nombre o usuario...",
        all: "Todos",
        admins: "Administradores",
        verified: "Verificados",
        inactive: "Inactivos",
        filter: "Filtrar",
        table_user: "Usuario",
        table_email: "Correo",
        table_participations: "Participaciones",
        table_prizes: "Premios",
        table_candidates: "Candidatos",
        table_contests: "Concursos",
        table_status: "Estado",
        table_actions: "Acciones",
        make_admin: "Hacer Admin",
        remove_admin: "Quitar Admin",
        activate: "Activar",
        deactivate: "Desactivar",
        no_users: "No se encontraron usuarios",
        registered: "Registrado",
        inactive_status: "Inactivo",
        user: "Usuario",
        email: "Correo",
        participations: "Participaciones",
        prizes: "Premios",
        candidates: "Candidatos",
        contests: "Concursos",
        status: "Estado",
        actions: "Acciones",
        details: "Detalles",
        comments: "Comentarios",
        view_comments: "Ver Comentarios",
        no_comments: "Sin comentarios",
        comment_text: "Texto",
        comment_date: "Fecha",
        comment_author: "Autor",
        city: "Ciudad",
        country: "País",
        continent: "Continente",
        region: "Región",
        kyc_status: "Estado KYC",
        kyc_verified: "Verificado",
        kyc_pending: "Pendiente",
        date_of_birth: "Fecha de Nacimiento",
        phone: "Teléfono",
        bio: "Biografía",
        last_login: "Último Acceso",
        joined: "Se Unió",
        participations_count: "Participaciones",
        prizes_count: "Premios",
        contestants_count: "Candidatos",
        contests_participated: "Concursos",
        confirm_delete_title: "Eliminar Usuario",
        confirm_delete_message: "¿Estás seguro de que deseas eliminar este usuario? Esta acción es irreversible.",
        delete: "Eliminar",
        cancel: "Cancelar",
        delete_success: "Usuario eliminado exitosamente",
        delete_error: "Error al eliminar usuario",
        personal_info: "Información Personal",
        account_status: "Estado de la Cuenta",
        verify_kyc: "Verificar KYC",
        unverify_kyc: "Revocar KYC",
        kyc_verify_success: "KYC verificado exitosamente",
        kyc_unverify_success: "Verificación KYC revocada",
        toggle_admin_success: "Derechos de administrador modificados",
        toggle_admin_error: "Error al modificar el rol del usuario",
        toggle_active_success_deactivate: "Usuario desactivado",
        toggle_active_success_activate: "Usuario activado",
        toggle_active_error: "Error al modificar el estado del usuario",
        load_error: "Error al cargar usuarios",
        load_details_error: "Error al cargar detalles",
        edit_comment: "Editar",
        delete_comment: "Eliminar",
        hide_comment: "Ocultar",
        show_comment: "Mostrar",
        comment_edit_success: "Comentario actualizado",
        comment_delete_success: "Comentario eliminado",
        comment_hide_success: "Comentario oculto",
        comment_show_success: "Comentario mostrado",
        comment_edit_error: "Error al actualizar comentario",
        comment_delete_error: "Error al eliminar comentario",
        comment_hide_error: "Error al ocultar comentario",
        comment_show_error: "Error al mostrar comentario",
        contest_label: "Concurso",
        contestant_label: "Candidato"
      },
      reports: {
        title: "Reportes",
        description: "Gestionar reportes de contenido",
        pending: "pendiente",
        reviewed: "revisado",
        resolved: "resuelto",
        search_placeholder: "Buscar por razón o tipo...",
        filter: "Filtrar",
        all: "Todos",
        no_reports: "No se encontraron reportes",
        reporter: "Reportador",
        reported_content: "Contenido Reportado",
        reason: "Razón",
        status: "Estado",
        date: "Fecha",
        actions: "Acciones",
        view: "Ver",
        mark_reviewed: "Marcar como Revisado",
        mark_resolved: "Marcar como Resuelto",
        details: "Detalles",
        close: "Cerrar",
        report_details: "Detalles del Reporte",
        reported_by: "Reportado por",
        reported_at: "Reportado el",
        report_reason: "Razón del Reporte",
        report_description: "Descripción",
        report_status: "Estado",
        moderator_notes: "Notas del Moderador",
        reviewed_by: "Revisado por",
        reviewed_at: "Revisado el",
        content_type: "Tipo de Contenido",
        contestant: "Candidato",
        comment: "Comentario",
        media: "Medio",
        user: "Usuario",
        mark_reviewed_success: "Reporte marcado como revisado",
        mark_reviewed_error: "Error al actualizar el reporte",
        mark_resolved_success: "Reporte marcado como resuelto",
        mark_resolved_error: "Error al actualizar el reporte",
        load_error: "Error al cargar los reportes"
      }
    },
    hero: {
      badge: "Plataforma de concursos #1 mundial",
      title_line1: "Únete a la mayor",
      title_line2: "comunidad de concursos",
      description: "Participa como concursante, nomina tu concursante favorito en tu país, o vota en cualquier concurso que te guste, y obtén recompensas mientras te diviertes.",
      title_line3: "del mundo",
      subtitle: "Participa como concursante, nomina tu concursante favorito en tu país, o vota en cualquier concurso que te guste, y obtén recompensas mientras te diviertes.",
      cta: "Comenzar ahora",
      demo: "Ver Demo",
      stats: {
        participants: "Participantes activos",
        contests: "Concursos organizados",
        countries: "Países representados"
      },
      trust: {
        secure: "Seguro y certificado",
        support: "Soporte 24/7",
        free: "Gratis para unirse"
      }
    },
    nav: {
      home: "Inicio",
      contests: "Concursos",
      rankings: "Rankings",
      community: "Comunidad",
      about: "Acerca de",
      login: "Iniciar Sesión",
      register: "Registrarse"
    },
    navigation: {
      home: "Inicio",
      landing: "Inicio",
      dashboard: "Panel de control",
      contests: "Concursos",
      clubs: "Clubes",
      about: "Acerca de",
      contact: "Contacto",
      login: "Iniciar Sesión",
      register: "Registrarse",
      download_app: "Descargar App"
    },
    header: {
      language: "Idioma",
      theme: "Tema"
    },
    auth: {
      email: "Correo electrónico",
      password: "Contraseña",
      username: "Nombre de usuario",
      forgotPassword: "¿Olvidaste tu contraseña?",
      loginError: "Error de inicio de sesión",
      registerError: "Error de registro",
      referral_detected: "¡Código de referido detectado!",
      referral_bonus: "¡Has sido referido!",
      referral_code: "Código",
      login: {
        title: "Iniciar Sesión",
        subtitle: "Accede a tu cuenta MyHigh5",
        email_placeholder: "Correo o nombre de usuario",
        password_placeholder: "Tu contraseña",
        forgot_password: "¿Olvidaste tu contraseña?",
        loading: "Iniciando sesión...",
        submit: "Iniciar Sesión",
        no_account: "¿No tienes cuenta?",
        register_link: "Registrarse",
        errors: {
          required_fields: "Todos los campos son obligatorios",
          invalid_credentials: "Correo/nombre de usuario o contraseña inválidos",
          timeout: "Tiempo de espera agotado. Inténtalo de nuevo.",
          network_error: "Error de conexión. Verifica tu conexión a internet.",
          service_unavailable: "El servicio se está iniciando. Espera un momento e inténtalo de nuevo."
        }
      },
      register: {
        title: "Registrarse",
        subtitle: "Crea tu cuenta MyHigh5 gratis",
        email_placeholder: "Tu dirección de correo",
        username_placeholder: "Nombre de usuario",
        username_hint: "Solo se permiten letras, números y guiones bajos",
        username_no_spaces_warning: "Caracteres no permitidos",
        username_space_not_allowed: "Los espacios no están permitidos",
        password_requirements_title: "La contraseña debe contener:",
        password_requirement_length: "Al menos 8 caracteres",
        password_requirement_uppercase: "Una letra mayúscula (A-Z)",
        password_requirement_lowercase: "Una letra minúscula (a-z)",
        password_requirement_number: "Un número (0-9)",
        password_requirement_special: "Un carácter especial (*_/@=)",
        password_placeholder: "Contraseña",
        confirm_password_placeholder: "Confirmar contraseña",
        full_name_placeholder: "Nombre completo (opcional)",
        phone_placeholder: "Número de teléfono",
        referral_code_placeholder: "Código de referido (opcional)",
        country: "País",
        country_placeholder: "Selecciona un país",
        city: "Ciudad",
        city_placeholder: "Escribe tu ciudad",
        loading: "Creando cuenta...",
        submit: "Crear Cuenta",
        have_account: "¿Ya tienes cuenta?",
        login_link: "Iniciar sesión",
        terms_accept: "Al registrarte, aceptas nuestros términos de servicio",
        success_title: "¡Registro exitoso!",
        success_message: "¡Bienvenido! Tu cuenta ha sido creada con éxito.",
        continue_button: "Iniciar sesión",
        errors: {
          required_fields: "Todos los campos obligatorios deben completarse",
          password_mismatch: "Las contraseñas no coinciden",
          password_min_length: "La contraseña debe tener al menos 8 caracteres",
          terms_required: "Debes aceptar los términos de servicio",
          email_exists: "Ya existe un usuario con este correo electrónico",
          username_exists: "Este nombre de usuario ya está en uso",
          invalid_email: "Formato de correo electrónico inválido",
          username_invalid_chars: "Solo se permiten letras, números y guiones bajos",
          password_requirements: "La contraseña debe contener una letra mayúscula, una letra minúscula, un número y un carácter especial (*_/@=)",
          location_required: "Por favor selecciona tu país y ciudad"
        }
      }
    },
    common: {
      loading: "Cargando...",
      error: "Error",
      success: "Éxito",
      network_error: "Error de conexión. Verifica tu conexión a internet.",
      cancel: "Cancelar",
      confirm: "Confirmar",
      continue: "Continuar",
      or: "O",
      redirecting: "¡Inicio de sesión exitoso! Redirigiendo al dashboard...",
      please_wait: "Por favor espera",
      back: "Atrás",
      back_to_dashboard: "Volver al Panel",
      previous: "Anterior",
      next: "Siguiente",
      submitting: "Enviando...",
      no_documents: "Sin documentos cargados",
      profile_setup: "Configuración de Perfil",
      profile_setup_description: "Completa tu perfil para participar en concursos",
      edit: "Editar",
      delete: "Eliminar",
      deleting: "Eliminando...",
      confirm_delete: "Confirmar Eliminación",
      deleted_successfully: "Eliminado exitosamente",
      likes: "Likes",
      comments: "Comentarios",
      search: "Buscar",
      clear: "Limpiar",
      optional: "opcional",
      coming_soon: "Próximamente",
      welcome: "Bienvenido",
      access_denied: "Acceso Denegado",
      no_permission: "No tienes permiso para acceder a esta página.",
      refresh: "Actualizar",
      view_more: "Ver más",
      unknown: "Desconocido",
      load_more: "Cargar más",
      actions: "Acciones"
    },
    affiliates: {
      grow_network: "Haz Crecer Tu Red",
      invite_friends: "Invita amigos y gana comisiones por sus actividades",
      invite_now: "Invitar Ahora",
      title: "Programa de Afiliados",
      your_link: "Tu Enlace de Afiliado",
      copy_link: "Copiar Enlace",
      link_copied: "¡Enlace copiado!",
      share: "Compartir",
      earnings: "Tus Ganancias",
      pending: "Pendiente",
      paid: "Pagado",
      referrals: "Referidos",
    },
    profile_setup: {
      location: "Ubicación",
      gender: "Género",
      date_of_birth: "Fecha de Nacimiento",
      male: "Hombre",
      female: "Mujer",
      other: "Otro",
      prefer_not_to_say: "Prefiero no decir",
      first_name: "Nombre",
      first_name_placeholder: "Tu nombre",
      first_name_required: "El nombre es requerido",
      last_name: "Apellido",
      last_name_placeholder: "Tu apellido",
      last_name_required: "El apellido es requerido",
      avatar: "Avatar",
      avatar_required: "El avatar es requerido",
      bio: "Bio",
      bio_placeholder: "Cuéntanos sobre ti...",
      bio_required: "La bio es requerida",
      characters: "caracteres",
      city_required: "La ciudad es requerida",
      continent_required: "El continente es requerido",
      region_required: "La región es requerida",
      country_required: "El país es requerido",
      gender_required: "El género es requerido",
      dob_required: "La fecha de nacimiento es requerida",
      session_expired: "Sesión expirada",
      update_error: "Error al actualizar el perfil",
      success: "¡Perfil configurado exitosamente!",
      continue: "Continuar",
      info: "Esta información es requerida para participar en concursos. Puedes modificarla más tarde en la configuración de tu perfil.",
      click_upload: "Haz clic para subir",
      preparing: "Preparando...",
      checking_files: "Verificando archivos...",
      uploading: "Subiendo...",
      images: "Imágenes",
      upload_error: "Error de carga"
    },
    settings: {
      title: "Configuración",
      description: "Administra tu información personal y preferencias",
      profile: "Perfil",
      profile_short: "Foto, nombre y bio",
      profile_description: "Edita tu foto, nombre y biografía",
      location: "Ubicación",
      location_short: "País y ciudad",
      location_description: "Define tu ubicación geográfica",
      demographics: "Identidad",
      demographics_short: "Género y edad",
      demographics_description: "Ingresa tu información personal",
      continent: "Continente",
      region: "Región",
      country: "País",
      city: "Ciudad",
      current_location: "Ubicación Actual",
      location_locked_title: "Ubicación Bloqueada",
      location_locked_message: "Ya has participado en un concurso. Tu ubicación no puede ser modificada.",
      save: "Guardar",
      remove: "Eliminar",
      profile_completion: "Perfil completado",
      missing: "Falta",
      referral_code_label: "Código de referido",
      admin: "Admin",
      verified: "Verificado",
      verify_identity: "Verificar mi identidad",
      years: "años",
      user: "Usuario",
      profile_photo: "Foto de perfil",
      biography: "Biografía",
      password: {
        title: "Contraseña",
        description: "Cambia tu contraseña para proteger tu cuenta",
        current: "Contraseña actual",
        new: "Nueva contraseña",
        confirm: "Confirmar nueva contraseña",
        current_required: "La contraseña actual es requerida",
        new_required: "La nueva contraseña es requerida",
        confirm_required: "La confirmación de la contraseña es requerida",
        min_length: "La contraseña debe tener al menos 6 caracteres",
        mismatch: "Las contraseñas no coinciden",
        same_password: "La nueva contraseña debe ser diferente a la anterior",
        session_expired: "Sesión expirada",
        success: "Contraseña cambiada exitosamente",
        error: "Error al cambiar la contraseña",
        saving: "Guardando...",
        save: "Cambiar contraseña",
        security_info: "Seguridad de tu cuenta",
        security_description: "Para proteger tu cuenta, usa una contraseña fuerte y única.",
        min_6_chars: "6 caracteres mínimo",
        uppercase: "Una mayúscula",
        lowercase: "Una minúscula",
        number: "Un número"
      },
      password_short: "Seguridad de la cuenta"
    },
    participation: {
      location: "Tu Ubicación",
      category: "Categoría",
      categoryPlaceholder: "Selecciona una categoría",
      title: "Título",
      title_placeholder: "Ingresa el título de tu participación",
      description: "Descripción",
      descriptionPlaceholder: "Describe tu participación, talentos, logros...",
      characters: "caracteres",
      media: "Medios (Imágenes/Videos)",
      images: "Imágenes",
      images_placeholder: "Haz clic para agregar imágenes",
      video: "Video",
      video_placeholder: "Haz clic para agregar un video",
      video_optional: "Video (opcional)",
      clickUpload: "Haz clic o arrastra tus archivos",
      preparing: "Preparando...",
      checkingFiles: "Verificando archivos...",
      uploading: "Subiendo...",
      imagesVideos: "Imágenes y videos",
      uploadError: "Error de carga",
      uploadedFiles: "Archivos cargados",
      submit: "Enviar mi participación",
      cancel: "Cancelar",
      profile_incomplete_title: "⚠️ Perfil Incompleto",
      profile_incomplete_message: "Debes completar tu perfil antes de participar en concursos. Por favor proporciona tu nombre, apellido, país y ciudad.",
      complete_profile_button: "Completar Mi Perfil",
      kyc_notification: "⚠️ Tu identidad no ha sido verificada. Te recomendamos completar tu verificación KYC para una mejor experiencia.",
      // URL import
      or: "o",
      add_by_url: "Agregar por URL",
      add_video_by_url: "Agregar por URL",
      add: "Agregar",
      image_url_placeholder: "https://ejemplo.com/imagen.jpg",
      video_url_placeholder: "https://youtube.com/watch?v=... o https://ejemplo.com/video.mp4",
      invalid_video_url: "Enlace no autorizado. Solo se aceptan YouTube y TikTok.",
      unsupported_platform: "Enlace no autorizado",
      open_link: "Abrir enlace",
      view_on_tiktok: "Ver en TikTok",
      view_on_youtube: "Ver en YouTube",
      only_youtube_tiktok: "Solo se aceptan YouTube y TikTok",
      invalid_url: "URL de video no válida",
      video_platform_not_allowed: "Plataforma de video no aceptada. Solo YouTube y TikTok son soportados.",
      video_file_not_allowed: "La carga de archivos de video no está permitida. Por favor use una URL de YouTube o TikTok.",
      youtube_shorts_not_allowed: "Los YouTube Shorts no están permitidos. Por favor use un video de YouTube estándar.",
      tiktok_preview_unavailable: "Vista previa no disponible — ver en TikTok",
      watch_on_tiktok: "Ver en TikTok",
      url_required: "URL requerida",
      invalid_url: "URL inválida",
      max_images_reached: "Número máximo de imágenes alcanzado",
      image_added: "Imagen agregada",
      video_added: "Video agregado",
      // Media requirements
      media_requirements: "Requisitos de medios",
      images_required: "Imágenes",
      video_required: "Video obligatorio",
      video_required_title: "Video *",
      // New labels
      content_title: "Título del Contenido",
      content_title_placeholder: "Ingrese el título del contenido (mínimo 10 caracteres)",
      content_description: "Descripción del Contenido",
      content_description_placeholder: "Ingrese la descripción del contenido (20-50 caracteres)",
      content_image: "Imagen del Contenido",
      content_video_required: "Video del Contenido *",
      content_video_optional: "Video del Contenido (opcional)",
      min_characters: "Mínimo",
      important_errors: "Errores Importantes a Corregir",
      // Nominator location fields
      nominator_location: "Ubicación del Candidato",
      nominator_location_description: "Por favor proporcione la ubicación de la persona que está nominando.",
      nominator_country: "País",
      nominator_country_note: "El país debe coincidir con el país de su perfil. Solo puede nominar candidatos de su propio país.",
      select_country: "Seleccione un país",
      nominator_city: "Ciudad",
      nominator_city_placeholder: "Ingrese el nombre de la ciudad",
      select_city: "Seleccione una ciudad",
      select_country_first: "Seleccione un país primero",
      ad_revenue_warning: "Advertencia: No recibirá el pago de los ingresos publicitarios generados por su contenido si detectamos que el contenido no proviene de su país.",
      // Stepper
      step_info: "Información",
      step_media: "Medios",
      step_review: "Verificación",
      time_remaining: "Tiempo de participación restante",
      deadline: "Fecha límite",
      submission_period_ended: "El período de envío ha terminado",
      review_title: "Verifique su candidatura",
      supported_platforms: "Plataformas soportadas",
      unrecognized_video_link: "Enlace de video no reconocido",
      // Errors
      errors: {
        content_title_required: "Título del Contenido",
        content_title_min_length: "El título del contenido debe contener al menos 5 caracteres",
        content_title_max_length: "El título del contenido no debe exceder 5 caracteres",
        content_description_required: "Descripción del Contenido",
        content_description_min_length: "La descripción del contenido debe contener al menos 20 caracteres",
        content_description_max_length: "La descripción del contenido no debe exceder 50 caracteres",
        content_image_required: "Imagen del Contenido",
        at_least_one_image: "Se requiere al menos una imagen",
        content_video_required: "Video del Contenido",
        video_required_for_contest: "Se requiere un video para este concurso",
        fill_all_fields: "Por favor complete todos los campos requeridos antes de enviar",
        nominator_country_required: "El país es requerido"
      }
    },
    moderation: {
      content_rejected: "⚠️ Contenido rechazado por moderación",
      adult_content: "Contenido para adultos detectado",
      violence_detected: "Contenido violento detectado",
      gore_detected: "Contenido gore/sangriento detectado",
      weapons_detected: "Arma detectada",
      offensive_content: "Contenido ofensivo detectado",
      ownership_failed: "Verificación de propiedad fallida",
      face_mismatch: "El rostro no coincide con tu verificación",
      analyzing: "Analizando contenido...",
      approved: "Contenido aprobado",
      rejected: "Contenido rechazado"
    },
    features: {
      title: "Características Excepcionales",
      subtitle: "Descubre todo lo que hace de MyHigh5 una plataforma de concursos en línea global única y emocionante.",
      items: {
        multi_level: {
          title: "Concursos Multi-Nivel",
          description: "Participa en competencias locales, nacionales e internacionales con un sistema de progresión único."
        },
        financial_rewards: {
          title: "Recompensas Financieras",
          description: "Recibe comisiones de afiliados por los ingresos generados por tu red de referidos, hasta 10 generaciones."
        },
        international_reach: {
          title: "Alcance Internacional",
          description: "Tus talentos pueden ser descubiertos y apreciados por una audiencia global diversa."
        },
        innovative_voting: {
          title: "Votación Innovadora",
          description: "Sistema de votación justo y transparente con clasificaciones en tiempo real."
        },
        varied_categories: {
          title: "Categorías Variadas",
          description: "Encuentra las categorías de concursos que te emocionan participar. Recomienda las categorías que te gustaría ver añadidas."
        }
      }
    },
    testimonials: {
      title: "Lo que dicen nuestros usuarios",
      favorites: {
        title: "Mis Favoritos",
        description: "Ver tus concursos y candidatos favoritos",
        contests_tab: "Concursos",
        contestants_tab: "Candidatos",
        no_favorite_contests: "Aún no tienes concursos favoritos",
        no_favorite_contestants: "Aún no tienes candidatos favoritos"
      },
      myhigh5: {
        title: "MyHigh5",
        description: "Los 5 concursantes por los que has votado",
        hint: "Tu primer voto se muestra en la posición 1 y tu voto más reciente en la posición 5. Puedes votar por un máximo de 5 concursantes.",
        no_votes: "Sin votos",
        no_votes_description: "Aún no has votado por ningún concursante. ¡Explora los concursos para votar!",
        explore_contests: "Explorar concursos",
        explore_more: "Explorar más concursos",
        remaining_votes: "Aún puedes votar por {count} concursante(s) más",
        votes_label: "votos",
        hint_dnd: "Arrastra y suelta para reordenar tus votos. El 1º recibe 5 puntos, el 2º 4 puntos, el 3º 3 puntos, el 4º 2 puntos y el 5º 1 punto. Los votos están limitados a 5 por temporada.",
        rank: "Rango",
        points: "Puntos",
        contestant: "Concursante",
        location: "Ubicación",
        total_votes: "Votos totales",
        vote_date: "Fecha del voto",
        order_saved: "¡Orden guardado!",
        order_error: "Error al guardar el orden",
        points_legend: "Sistema de puntos",
        points_label: "puntos"
      },
      subtitle: "Únete a miles de participantes satisfechos que han transformado su pasión en éxito.",
      cta: "Únete a miles de participantes satisfechos",
      users: "+1M usuarios",
      items: {
        marie: {
          name: "Marie Dubois",
          text: "MyHigh5 me permitió descubrir mi talento y conocer una comunidad increíble. ¡Gané 3 concursos este año!",
          role: "Ganadora Concurso Belleza",
          rating: 5,
          location: "París, Francia"
        },
        jean: {
          name: "Jean Martin",
          text: "La interfaz es intuitiva y los concursos son variados. Se ha convertido en mi plataforma favorita para expresar mi creatividad.",
          role: "Participante Activo",
          rating: 5,
          location: "Lyon, Francia"
        },
        sophie: {
          name: "Sophie Laurent",
          text: "Gracias al programa de afiliados, creé una fuente adicional de ingresos mientras me divertía.",
          role: "Embajadora MyHigh5",
          rating: 5,
          location: "Marsella, Francia"
        },
        sarah_m: {
          name: "Sarah Martín",
          text: "¡Una experiencia increíble! Descubrí mi pasión por la fotografía a través de los concursos de MyHigh5.",
          role: "Fotógrafa Amateur",
          rating: 5,
          location: "Barcelona, España"
        },
        carlos_r: {
          name: "Carlos Rodríguez",
          text: "La comunidad es fantástica y muy alentadora. ¡Mis talentos de baile han sido reconocidos internacionalmente!",
          role: "Bailarín Profesional",
          rating: 5,
          location: "Madrid, España"
        },
        emma_l: {
          name: "Emma Laurent",
          text: "MyHigh5 me dio la confianza para compartir mis creaciones. ¡Ahora tengo mi propia tienda en línea!",
          role: "Artista Creativa",
          rating: 5,
          location: "Bruselas, Bélgica"
        }
      }
    },
    cta: {
      title: "¿Listo para comenzar tu aventura?",
      subtitle: "Únete a millones de participantes y descubre tu potencial hoy.",
      button: "Crear mi cuenta gratuita",
      features: {
        instant: "Registro instantáneo",
        global: "Comunidad global",
        secure: "100% seguro",
        free_contests: "Concursos gratuitos",
        active_community: "Comunidad activa",
        real_rewards: "Recompensas reales"
      },
      trust: {
        instant: "Registro en 30 segundos",
        secure: "Sin tarjeta de crédito requerida",
        support: "Soporte 24/7"
      }
    },
    landing: {
      ways_to_earn: {
        badge: "Gana dinero",
        title: "Diferentes formas de ganar",
        subtitle: "Únete a nuestro programa de afiliados y gana comisiones en múltiples fuentes de ingresos",
        kyc_payments: {
          title: "Pagos KYC",
          description: "Gana comisiones cuando los miembros de tu red completen su verificación KYC",
          commission: "10% en Nivel 1, 1% en Niveles 2-10"
        },
        founding_membership: {
          title: "Membresía Fundadora",
          description: "Gana comisiones cuando los miembros de tu red de referidos se unan al Club de Miembros Fundadores o paguen la tarifa de membresía anual.",
          commission: "10% en Nivel 1, 1% en Niveles 2-10"
        },
        annual_membership: {
          title: "Tarifa de Membresía Anual",
          description: "Gana comisiones cuando los Miembros Fundadores pagan su tarifa de membresía anual.",
          commission: "10% en Nivel 1, 1% en Niveles 2-10"
        },
        club_memberships: {
          title: "Membresías de clubes",
          description: "Gana comisiones en las tarifas de membresía de clubes pagadas. El sitio web agrega un margen de beneficio del 20% a las tarifas especificadas por el propietario del club, de las cuales el 10% se paga al Nivel 1, y el 1% se paga a cada uno de los Niveles 2 a 10.",
          commission: "10% en Nivel 1, 1% en Niveles 2-10"
        },
        shop_purchases: {
          title: "Compras en la tienda",
          description: "Gana comisiones en compras de contenido digital en la tienda MyHigh5. El sitio web agrega un margen de beneficio del 20% a las tarifas especificadas por el propietario del club, de las cuales el 10% se paga al Nivel 1, y el 1% se paga a cada uno de los Niveles 2 a 10.",
          commission: "10% en Nivel 1, 1% en Niveles 2-10"
        },
        ad_revenue: {
          title: "Compartir ingresos publicitarios",
          description: "Los participantes en concursos ganan el 40% de los ingresos publicitarios generados en sus páginas de concursos. Sus patrocinadores de Nivel 1 ganan 5%, y los Niveles 2 a 10 ganan 1% cada uno. Los miembros que nominan candidatos ganan 10% de los ingresos publicitarios generados por sus candidatos nominados. Sus patrocinadores de Nivel 1 ganan 2.5%, y los Niveles 2 a 10 ganan 1% cada uno.",
          commission: "Participantes: 40% para uno mismo, 5% para el Nivel 1, 1% para cada uno de los Niveles 2 a 10.\nNominadores: 10% para uno mismo, 2.5% para el Nivel 1, 1% para cada uno de los Niveles 2 a 10."
        },
        ad_campaigns: {
          title: "Página de Patrocinadores del Sitio Web",
          description: "Los patrocinadores de Nivel 1 ganan una comisión del 10%, y los Niveles 2 a 10 ganan 1% cada uno.",
          commission: "10% en Nivel 1, 1% en Niveles 2-10"
        }
      },
      faq: {
        badge: "Preguntas frecuentes",
        title: "Preguntas frecuentes",
        subtitle: "Encuentra respuestas a las preguntas más comunes sobre MyHigh5",
        question_1: "¿Cómo puedo ganar dinero en MyHigh5?",
        answer_1: "Puedes ganar dinero de varias maneras: participando en concursos, nominando candidatos, uniéndote al programa de afiliados para ganar comisiones por los miembros que refieras, y convirtiéndote en miembro fundador para participar en los fondos de ingresos y ganancias.",
        question_2: "¿Cómo funciona el programa de afiliados?",
        answer_2: "• Pagos de tarifas de verificación:\n  Ganas una comisión del 10% en los pagos realizados por tus referidos directos, y una comisión del 1% en los pagos realizados por cada uno de tus referidos indirectos del Nivel 2 al Nivel 10.\n\n• Ingresos publicitarios (Candidatos participantes):\n  Los candidatos participantes reciben el 40% de los ingresos publicitarios generados en sus páginas de concursos. El patrocinador directo de un candidato participante recibe 5%, y cada patrocinador indirecto del Nivel 2 al Nivel 10 recibe 1%.\n\n• Ingresos publicitarios (Miembros que nominan):\n  Los miembros que nominan reciben 10% de los ingresos publicitarios generados en las páginas de concursos de sus candidatos nominados, 2.5% de los ingresos publicitarios generados en las páginas de concursos de candidatos nominados por sus referidos directos, y 1% de los ingresos publicitarios generados en las páginas de concursos de candidatos nominados por cada uno de sus referidos indirectos del Nivel 2 al Nivel 10.\n\n• Ingresos publicitarios (Clubes):\n  Los propietarios de clubes reciben 20% de los ingresos publicitarios generados en sus páginas de club o de fans. El patrocinador directo de un propietario de club recibe 5%, y cada patrocinador indirecto del Nivel 2 al Nivel 10 recibe 0.5%.\n\n• Tarifas de membresía de clubes:\n  MyHigh5 aplica un margen de beneficio del 10% a la tarifa de suscripción seleccionada por el miembro. De este margen, 10% se paga al patrocinador directo del pagador, y 1% se paga a cada patrocinador indirecto del Nivel 2 al Nivel 10.\n\n• Espacios en la página de Patrocinadores del Sitio Web:\n  Para los espacios pagados en la página de Patrocinadores del Sitio Web, 10% se paga al patrocinador de Nivel 1, y 1% se paga a cada uno de los patrocinadores de los Niveles 2 a 10.",
        question_3: "¿Qué es el estatus de Miembro Fundador?",
        answer_3: "El estatus de Miembro Fundador (MFM) es una oportunidad limitada que requiere la verificación de la cuenta y el pago de una tarifa de inscripción de $100 y una tarifa de membresía anual de club de $50 para los primeros 1,000 MFM, y una tarifa de inscripción de $200 y una tarifa de membresía anual de club de $200 a partir de entonces. Los espacios MFM dejarán de existir una vez que el número total de MFM alcance 10,000. Los Miembros Fundadores participan en fondos de comisiones mensuales equivalentes al 10% de los ingresos netos y un fondo de ganancias anual equivalente al 20% de las ganancias después de impuestos, asignados en función de la proporción de sus referidos verificados de Nivel 1 en relación con el número total de referidos verificados de Nivel 1.",
        question_4: "¿Cómo puedo participar en concursos?",
        answer_4: "Para participar en concursos, necesitas crear una cuenta gratuita, completar tu perfil, y enviar tu solicitud con fotos o videos según los requisitos del concurso. Algunos concursos pueden requerir verificación KYC.",
        question_5: "¿Los concursos son gratuitos?",
        answer_5: "Sí. La participación en concursos es gratuita, pero tu cuenta debe estar verificada porque necesitamos hacer coincidir el contenido de tu participación con tu identidad verificada. No necesitas verificar tu cuenta para nominar candidatos.",
        question_6: "¿Cómo puedo retirar mis ganancias?",
        answer_6: "Puedes retirar tus ganancias a través de tu billetera en el panel de control. Los pagos se procesan mensualmente, con un umbral mínimo de pago de $100. Los métodos de pago incluyen transferencia bancaria, PayPal, o criptomoneda."
      },
      download_app: {
        badge: "Aplicación móvil",
        title: "Descarga la aplicación MyHigh5",
        subtitle: "Participa en concursos, vota y gana dinero donde quiera que estés con nuestra aplicación móvil",
        scan_qr: "Escanear para descargar",
        download_on: "Descargar en",
        app_store: "App Store",
        available_on: "Disponible en",
        google_play: "Google Play",
        access_24_7: "Acceso 24/7",
        free: "Gratis"
      }
    },
    footer: {
      description: "La plataforma de concursos más popular del mundo. Participa, vota y gana en competencias emocionantes.",
      copyright: " 2024 MyHigh5. Todos los derechos reservados.",
      newsletter: {
        title: "Mantente actualizado sobre nuevos concursos",
        subtitle: "Recibe las últimas noticias y oportunidades directamente en tu bandeja de entrada.",
        placeholder: "Tu dirección de correo",
        subscribe: "Suscribirse",
        terms: "Al suscribirse, aceptas nuestros términos de uso y política de privacidad."
      },
      brand: {
        countries: "Disponible en 200+ países",
        support: "Soporte 24/7",
        email: "infos@myhigh5.com"
      },
      quick_links: {
        title: "Enlaces Rápidos",
        about: "Acerca de",
        contests: "Concursos",
        how_it_works: "Cómo funciona",
        affiliate: "Programa de afiliados",
        support: "Soporte"
      },
      categories: {
        title: "Categorías",
        beauty: "Concursos de Belleza",
        handsome: "Concursos de Atractivo",
        latest_hits: "Últimos Éxitos",
        pets: "Mascotas",
        sports_clubs: "Clubes Deportivos",
        no_categories: "No hay categorías disponibles"
      },
      legal: {
        title: "Legal",
        privacy: "Política de Privacidad",
        terms: "Términos de Servicio",
        cookies: "Política de Cookies",
        gdpr: "Cumplimiento RGPD"
      }
    },
    dashboard: {
      welcome: "Bienvenido",
      subtitle: "Descubre tu panel personalizado",
      search: {
        placeholder: "Buscar...",
        title: " Búsqueda",
        description: "Encuentra concursos, participantes, clubes y productos",
        no_results: "No se encontraron resultados",
        start_typing: "Comienza a escribir para buscar...",
        contest: "Concurso",
        contestant: "Participante",
        club: "Club",
        product: "Producto",
        recent_searches: "Búsquedas recientes",
        no_history: "No hay búsquedas recientes."
      },
      nav: {
        home: "Inicio",
        overview: "Resumen",
        contests: "Concursos",
        my_applications: "Mis Candidaturas",
        clubs: "Clubes",
        myhigh5: "MyHigh5",
        favorites: "Favoritos",
        search: "Búsqueda",
        pages: "Páginas",
        wallet: "Billetera",
        affiliates: "Afiliados",
        commissions: "Comisiones",
        leaderboard: "Clasificación",
        prize: "Premio",
        shop: "Tienda",
        main: "Principal",
        competitions: "Competiciones",
        business: "Negocios",
        resources: "Recursos",
        founding_member: "Founding Membership",
        affiliate_program: "Programa de Afiliación",
        affiliate_agreement: "Acuerdo de Afiliación",
        account: "Cuenta",
        settings: "Configuración",
        admin: "Administración",
        admin_panel: "Panel de Admin",
        admin_panel_desc: "Gestionar la plataforma",
        notifications: "Notificaciones",
        notifications_desc: "Ver todas tus notificaciones"
      },
      stats: {
        contests: "Mis Concursos",
        clubs: "Mis Clubes",
        favorites: "Mis Favoritos",
        points: "Mis Puntos"
      },
      analytics: {
        hello: "Hola",
        overview: "Aquí tienes un resumen de tu rendimiento",
        performance: "Rendimiento",
        affiliates: "Afiliados",
        total_votes: "Votos",
        likes: "Me gusta",
        comments: "Comentarios",
        total_views: "Vistas",
        reactions: "Reacciones",
        direct_affiliates: "Afiliados Directos",
        total_network: "Red Total",
        commissions: "Comisiones",
        conversion_rate: "Tasa de Conversión",
        contest_performance: "Rendimiento por Concurso",
        contest_performance_desc: "Votos y engagement de tus candidaturas",
        reactions_distribution: "Reacciones",
        reactions_distribution_desc: "Distribución por tipo",
        weekly_activity: "Actividad Semanal",
        weekly_activity_desc: "Votos y vistas esta semana",
        network_growth: "Crecimiento de la Red",
        network_growth_desc: "Evolución de tus afiliados",
        monthly_commissions: "Comisiones Mensuales",
        monthly_commissions_desc: "Ingresos generados por tu red",
        active_contests: "Concursos Activos",
        best_ranking: "Mejor Clasificación",
        engagement: "Engagement",
        this_month: "Este mes",
        total: "Total",
        last_7_days: "7 días",
        view_stats: "Ver estadísticas",
        statistics: "Estadísticas",
        days: {
          monday: "Lunes",
          tuesday: "Martes",
          wednesday: "Miércoles",
          thursday: "Jueves",
          friday: "Viernes",
          saturday: "Sábado",
          sunday: "Domingo",
          mon: "Lun",
          tue: "Mar",
          wed: "Mié",
          thu: "Jue",
          fri: "Vie",
          sat: "Sáb",
          sun: "Dom"
        },
        months: {
          january: "Enero",
          february: "Febrero",
          march: "Marzo",
          april: "Abril",
          may: "Mayo",
          june: "Junio",
          july: "Julio",
          august: "Agosto",
          september: "Septiembre",
          october: "Octubre",
          november: "Noviembre",
          december: "Diciembre",
          jan: "Ene",
          feb: "Feb",
          mar: "Mar",
          apr: "Abr",
          may_short: "May",
          jun: "Jun",
          jul: "Jul",
          aug: "Ago",
          sep: "Sep",
          oct: "Oct",
          nov: "Nov",
          dec: "Dic"
        }
      },
      wallet: {
        title: "Mi Billetera",
        subtitle: "Gestiona tus ingresos y transacciones",
        available_balance: "Saldo disponible",
        pending_balance: "Pendiente",
        pending_description: "Fondos en validación",
        total_earnings: "Ganancias totales",
        since_registration: "Desde tu registro",
        this_month: "este mes",
        history: "Historial",
        withdraw: "Retirar",
        add_funds: "Agregar",
        redeem: "Canjear",
        cards: "Tarjetas",
        recent_transactions: "Transacciones recientes",
        all_transactions: "Todas las transacciones",
        transactions_subtitle: "Historial completo de tus transacciones",
        see_all: "Ver todo",
        completed: "Completado",
        approved: "Aprobado",
        pending: "Pendiente",
        failed: "Fallido",
        expired: "Expirado",
        commission: "Comisión",
        purchase: "Compra",
        all: "Todo",
        commissions: "Comisiones",
        purchases: "Compras",
        filter_by_type: "Filtrar por tipo",
        export: "Exportar",
        no_transactions: "Sin transacciones",
        no_transactions_desc: "Aún no tienes transacciones",
        pay: "Pagar",
        invoice: "Factura",
        commission_affiliate: "Comisión de afiliado",
        welcome_bonus: "Bono de bienvenida",
        bank_withdrawal: "Retiro bancario",
        premium_votes: "Compra de votos premium"
      },
      affiliates: {
        title: "Programa de Afiliados",
        subtitle: "Refiere y gana comisiones",
        invite: "Invitar",
        total_affiliates: "Total afiliados",
        direct_affiliates: "Afiliados directos",
        total_commissions: "Comisiones",
        conversion_rate: "Tasa conversión",
        your_referral_link: "Tu enlace de referido",
        your_referral_links: "Tus enlaces de referido",
        link_register: "Enlace de registro",
        link_home: "Enlace página inicio",
        link_contestants: "Enlace página concursos",
        your_code: "Tu código",
        copy: "Copiar",
        copied: "¡Copiado!",
        share: "Compartir",
        view_links: "Ver enlaces",
        share_description: "Comparte tus enlaces y gana comisiones por cada registro",
        links_description: "Copia y comparte estos enlaces para referir nuevos usuarios",
        your_sponsor: "Tu patrocinador",
        no_sponsor: "Sin patrocinador",
        commission_tiers: "Niveles de comisión",
        commission_description: "Descubre nuestros 10 niveles de comisión",
        view_commissions: "Ver detalles",
        total_potential: "Total potencial",
        max_commission: "Comisión máxima en 10 niveles",
        level: "Nivel",
        direct_referrals: "Referidos directos",
        second_level: "Segundo nivel",
        third_level: "Tercer nivel",
        your_affiliates: "Tus afiliados",
        see_all: "Ver todo",
        active: "Activo",
        joined: "Se unió",
        earnings: "Ganancias generadas",
        no_affiliates: "Sin afiliados aún",
        start_inviting: "Empieza a invitar amigos para ganar comisiones",
        invite_friends: "Invitar amigos",
        ten_levels: "10 niveles de comisión",
        commission: "Comisión",
        no_commission: "Sin comisión",
        kyc_pending: "KYC pendiente",
        commission_rate: "20% en pagos KYC",
        commission_structure: "Estructura de comisiones KYC",
        all_kyc_statuses: "Todos KYC",
        kyc_status_label: "Estado KYC",
        kyc_none: "No iniciado",
        kyc_in_progress: "En progreso",
        kyc_approved: "Verificado",
        kyc_rejected: "Rechazado",
        kyc_expired: "Expirado",
        kyc_requires_review: "Requiere revisión",
        kyc_verified: "KYC Verificados",
        direct_referrals: "Directos (Niv. 1)",
        indirect_referrals: "Indirectos (Niv. 2-10)",
        direct_tooltip_title: "Referidos Directos",
        direct_tooltip_desc: "Usuarios que referiste directamente (nivel 1). Ganas 20% de comisión en sus pagos KYC.",
        indirect_tooltip_title: "Referidos Indirectos",
        indirect_tooltip_desc: "Usuarios referidos por tus referidos (niveles 2-10). Ganas 2% de comisión en sus pagos KYC.",
        earned: "Ganado",
        total_tooltip_title: "Total Afiliados",
        total_tooltip_desc: "Número total de personas en tu red de afiliados, todos los niveles combinados (1 a 10).",
        active_tooltip_title: "Afiliados Activos",
        active_tooltip_desc: "Usuarios con una cuenta activa que pueden generar comisiones.",
        kyc_verified_tooltip_title: "KYC Verificados",
        kyc_verified_tooltip_desc: "Afiliados que han completado exitosamente la verificación de identidad (KYC aprobado).",
        commissions_tooltip_title: "Total Comisiones",
        commissions_tooltip_desc: "Suma de todas las comisiones ganadas a través de tu red de afiliados.",
        col_affiliate_hint: "Información sobre el miembro de tu red",
        col_level_hint: "Nivel 1 = directo (20%), Niveles 2-10 = indirecto (2%)",
        col_kyc_hint: "Estado de verificación de identidad (comisión recibida si aprobado)",
        col_referrals_hint: "Número de personas referidas por este afiliado",
        col_earnings_hint: "Comisión que ganaste gracias a este afiliado",
        col_status_hint: "Estado de la cuenta de usuario (activo o inactivo)",
        levels: "Niveles",
        direct_commission: "Comisión directa",
        indirect_commission: "Comisiones indirectas",
        indirect_description: "Gana 2% en cada nivel de tu red, hasta el nivel 10.",
        cookie_tracking: "Seguimiento por cookies: 30 días",
        all_affiliates: "Todos los afiliados",
        affiliates_found: "afiliados encontrados",
        search_placeholder: "Buscar por nombre o email...",
        all_levels: "Todos los niveles",
        all_statuses: "Todos los estados",
        inactive: "Inactivo",
        affiliate: "Afiliado",
        referrals_count: "Referidos",
        status: "Estado",
        total_referrals: "Total referidos",
        no_results: "Sin resultados",
        try_different_filters: "Prueba con filtros diferentes",
        showing: "Mostrando",
        of: "de",
        pending_invitations: "Pendiente",
        invite_friend: "Invitar a un amigo",
        invite_description: "Envía una invitación por correo electrónico para referir a tus amigos",
        email_address: "Dirección de correo electrónico",
        personal_message: "Mensaje personal",
        message_placeholder: "¡Hola! Únete a mí en MyHigh5...",
        send_invitation: "Enviar invitación",
        sending: "Enviando...",
        share_link: "Comparte tu enlace",
        code_label: "Código",
        link_copied: "¡Enlace copiado!",
        invite_sent_success: "¡Invitación enviada con éxito!",
        invite_error: "Error al enviar la invitación",
        invite_email_required: "Por favor ingresa un correo electrónico",
        pending: "Pendiente",
        sent_on: "Enviado el",
        cancel: "Cancelar",
        invitation_cancelled: "Invitación cancelada",
        no_pending: "No hay invitaciones pendientes",
        send_invitation_desc: "Envía invitaciones a tus amigos para referirlos",
        copy_error: "Error al copiar",
        cancel_error: "Error al cancelar"
      }
    },
    dashboard: {
      welcome: "Bienvenido",
      subtitle: "Sigue tu progreso, gestiona tus concursos y haz crecer tu red",
      quick_actions: "Acciones Rápidas",
      recent_activity: "Actividad Reciente",
      no_activity: "Sin actividad reciente",
      position: {
        title: "Mi Posición",
        no_contests: "Sin concursos activos",
        rank: "Rango",
        points: "Puntos",
        contests: "Concurso de Belleza",
        clubs: "Club Premium",
        affiliates: "Afiliados",
        status: "Estado",
        members: "Miembros",
        referrals: "Referidos",
        commissions: "Comisiones",
        active: "Activo"
      },
      contests: {
        title: "Concursos",
        subtitle: "Descubre y participa en concursos de tu ciudad y país",
        description: "Descubre y participa en los concursos más populares",
        no_contests: "No hay concursos disponibles",
        no_description: "No hay descripción disponible",
        all: "Todos",
        nomination: "Nominaciones",
        participations: "Participaciones",
        filter_level: "Nivel",
        level_city: "Ciudad",
        level_country: "País",
        all_levels: "Todos los niveles",
        nomination_hint: "Nomina a otras personas para que participen en competencias. Vota por los concursantes nominados por sus fans.",
        participations_hint: "Participa tú mismo en competencias. Los concursantes se inscriben directamente para competir.",
        nominate: "Nominar",
        edit_nomination: "Editar tu Nominación",
        edit_participation: "Editar tu Participación",
        edit: "Editar",
        tooltip_nominate: "Haz clic para nominar en este concurso y enviar tu candidatura",
        time_remaining_to_nominate: "Tiempo restante para nominar",
        search_placeholder: "Buscar un concurso...",
        search_button: "Buscar",
        sort: "Ordenar por",
        sort_participants: "Más participantes",
        sort_votes: "Más votos",
        sort_date: "Más reciente",
        sort_name: "Nombre (A-Z)",
        voting_type: "Tipo de voto",
        voting_level_country: "Nacional",
        voting_level_city: "Ciudad",
        voting_level_regional: "Regional",
        voting_level_continent: "Continental",
        voting_level_global: "Global",
        status: "Estado",
        level: "Nivel",
        city: "Ciudad",
        country: "Nacional",
        continental: "Continental",
        regional: "Regional",
        global: "Global",
        contestants: "Participantes",
        likes: "Me gusta",
        comments: "Comentarios",
        received: "Recibido",
        participate: "Participar",
        contest_type: {
          beauty: "Belleza",
          handsome: "Guapo",
          latest_hits: "Últimos Éxitos",
          talent: "Talento",
          photography: "Fotografía",
          fitness: "Fitness",
          fashion: "Moda",
          music: "Música",
          dance: "Baile",
          cooking: "Cocina",
          art: "Arte",
          comics: "Cómics",
          other: "Otro"
        },
        men: "Hombres",
        women: "Mujeres",
        add_favorite: "Añadir a favoritos",
        remove_favorite: "Eliminar de favoritos",
        added_to_favorites: "Añadido a favoritos",
        removed_from_favorites: "Eliminado de favoritos",
        open: "Abierto",
        open_for_candidacy: "Abierto para candidaturas",
        closed: "Cerrado",
        submission_closed: "Las inscripciones están cerradas para este concurso.",
        submission_closed_message: "La fecha límite de envío ha pasado.",
        no_active_rounds: "No hay rondas activas que acepten envíos en este momento.",
        description: "Descripción",
        requirements: "Requisitos",
        kyc_required: "Verificación de identidad",
        kyc_required_description: "Solo los participantes con identidad verificada pueden participar en este concurso",
        visual_verification: "Foto tuya requerida",
        visual_verification_description: "Se requiere una foto tuya para participar en este concurso",
        voice_verification: "Verificación de voz",
        voice_verification_description: "Se requiere verificación de voz para participar en este concurso",
        brand_verification: "Marca verificada",
        brand_verification_description: "Solo las marcas verificadas pueden participar en este concurso",
        content_verification: "Contenido original requerido",
        content_verification_description: "Solo se permite contenido original para participar en este concurso",
        gender_restriction: "Restricción de género",
        gender_restriction_female_description: "Solo las participantes femeninas pueden participar en este concurso",
        gender_restriction_male_description: "Solo los participantes masculinos pueden participar en este concurso",
        age_restriction: "Restricción de edad",
        age_restriction_description: "Solo los participantes dentro del rango de edad especificado pueden participar",
        tooltip_info: "Ver detalles y condiciones del concurso",
        tooltip_time_remaining: "Tiempo restante antes del cierre del concurso",
        tooltip_gender_restriction_female: "Este concurso es solo para mujeres",
        tooltip_gender_restriction_male: "Este concurso es solo para hombres",
        tooltip_level_city: "Concurso a nivel de ciudad",
        tooltip_level_country: "Concurso a nivel nacional",
        tooltip_level_regional: "Concurso a nivel regional",
        tooltip_level_continental: "Concurso a nivel continental",
        tooltip_level_global: "Concurso a nivel mundial",
        tooltip_open: "Las inscripciones están abiertas. Puedes participar en este concurso.",
        tooltip_contestants: "Número de participantes en este concurso",
        tooltip_votes: "Número total de votos recibidos",
        tooltip_participate: "Haz clic para concursar en este concurso y enviar tu candidatura",
        tooltip_view_contestants: "Ver todos los participantes de este concurso",
        tooltip_view_contestants_closed: "El concurso está cerrado. Ver participantes del concurso",
        tooltip_view_contestants_cannot_participate: "No puedes concursar en este momento. Ver participantes del concurso",
        tooltip_closed: "El concurso está cerrado. Las inscripciones ya no se aceptan.",
        tooltip_voting_open: "La votación está abierta. Puedes votar por los participantes.",
        tooltip_rank: "Clasificación en este concurso",
        tooltip_author: "Ver perfil del participante",
        tooltip_votes_author: "Votos recibidos. Pasa el cursor para ver la lista de votantes.",
        years: "años",
        contest_info: "Información del concurso",
        contest_dates: "Fechas del concurso",
        submission_start: "Inicio de inscripciones",
        submission_end: "Fin de inscripciones",
        voting_start: "Inicio de votación",
        participant_type: "Tipo de participante",
        participant_individual: "Individual",
        participant_pet: "Mascota",
        participant_club: "Club",
        participant_content: "Contenido",
        male_only: "Solo Hombres",
        female_only: "Solo Mujeres",
        max_favorites: "5 favoritos máximo",
        favorite_limit_reached: "Límite de favoritos alcanzado",
        top_participants: "Top Participantes",
        top_5_description: "Los 5 mejores participantes del concurso",
        view: "Ver",
        contestant: "participante",
        view_contestants: "Ver participantes",
        view_all_contestants: "Ver todos los participantes",
        top_contestants: "Top Contestants",
        view_contestants_count: "participante",
        view_contestants_empty: "Sin participantes",
        view_contestants_description: "Descubre todos los participantes y vota por tus favoritos",
        time_remaining: "Tiempo restante",
        time_remaining_to_participate: "Tiempo restante para concursar",
        time_unit_days: "d",
        time_unit_hours: "h",
        time_unit_minutes: "m",
        time_unit_seconds: "s",
        candidacy_ends: "Fin de candidaturas",
        participation_ongoing: "Las candidaturas aún están abiertas",
        vote: "Votar",
        view_details: "Ver Detalles",
        already_voted: "Ya votado",
        cannot_vote: "No puedes votar por este participante",
        owner_cannot_vote: "Propietario, no puede votar",
        own_cannot_vote: "Propia candidatura, no puede votar",
        votes: "votos",
        shares: "Compartidos",
        submission: "Envío",
        voting: "Votación",
        start: "Inicio",
        end: "Fin",
        add_to_favorites: "Añadir a favoritos",
        remove_from_favorites: "Eliminar de favoritos",
        reaction_added: "Reacción añadida",
        reaction_removed: "Reacción eliminada",
        no_reactions: "Sin reacciones",
        no_votes: "Sin votos",
        no_favorites: "Sin favoritos",
        reply: "Responder",
        reply_placeholder: "Escribir una respuesta...",
        show_replies: "Ver {count} respuesta(s)",
        hide_replies: "Ocultar {count} respuesta(s)",
        like_added: "Me gusta agregado",
        like_removed: "Me gusta eliminado",
        comment_added: "Comentario agregado",
        reply_added: "Respuesta agregada",
        more: "más",
        loading: "Cargando...",
        votes: "Votos",
        favorites: "Favoritos",
        points: "puntos",
        share: "Compartir",
        share_title: "Compartir este participante",
        share_description: "Comparte este participante con tus amigos y tu red",
        share_link_label: "Enlace de compartir",
        copy: "Copiar",
        copied: "Copiado",
        share_natively: "Compartir nativamente",
        report: "Reportar",
        reactions: "Reacciones",
        you_reacted: "Has reaccionado",
        no_reactions: "No hay reacciones aún",
        people_reacted: "personas han reaccionado",
        be_first_to_react: "Sé el primero en reaccionar",
        participant: "Participante",
        rank: "Clasificación",
        reaction: "Reacción",
        search_contestant: "Buscar un participante...",
        filtered_by_country: "Filtrado por su país",
        no_contestants: "Aún no hay participantes",
        no_contestants_found: "No se encontraron participantes",
        like: "Me gusta",
        love: "Me encanta",
        wow: "Wow",
        dislike: "No me gusta",
        favorite: "Favorito",
        comments_description: "Comparte tus pensamientos sobre este participante",
        add_comment_placeholder: "Agregar un comentario...",
        sending: "Enviando...",
        send: "Enviar",
        no_comments: "No hay comentarios aún",
        cancel: "Cancelar",
        mention_hint: "Escribe @ para mencionar a alguien",
        edit: "Editar",
        delete: "Eliminar",
        vote_error: "Error al votar. Por favor, inténtalo de nuevo.",
        voting_not_open: "La votación aún no está abierta para este concurso.",
        already_voted_error: "Ya votado.",
        cannot_vote_own: "No puedes votar por tu propia candidatura.",
        vote_success: "¡Voto registrado con éxito!",
        vote_replaced: "¡Voto reemplazado con éxito!",
        my_votes: "Mis votos",
        no_votes_yet: "¡Vota por tus concursantes favoritos!",
        replace_vote_title: "Reemplazar un voto",
        replace_vote_message: "Ya tienes 5 votos. ¿Quieres reemplazar a",
        replace_vote_position: "(5ª posición, 1 punto) por este participante?",
        replace_vote_confirm: "Reemplazar",
        max_votes_reached: "Has alcanzado el máximo de 5 votos",
        empty_slot: "Espacio vacío",
        votes_remaining: "{n} voto(s) restante(s)",
        drag_to_reorder: "Arrastra para reordenar",
        vote_gender_restriction_male: "Este concurso está reservado para participantes masculinos. Solo las participantes femeninas pueden votar.",
        vote_gender_restriction_female: "Este concurso está reservado para participantes femeninas. Solo los participantes masculinos pueden votar.",
        vote_gender_not_set: "Su perfil no contiene información de género. Por favor complete su perfil para votar en este concurso.",
        gender: "Género",
        age: "Edad",
        years: "años",
        country: "País",
        city: "Ciudad",
        bio: "Biografía",
        rank: "Clasificación",
        votes: "Votos",
        male: "Hombre",
        female: "Mujer",
        my_applications: {
          title: "Mis Candidaturas",
          description: "Ver tus candidaturas y clasificación",
          no_applications: "Aún no tienes candidaturas",
          browse_contests: "Explorar concursos",
          status: "Estado",
          status_pending: "Pendiente",
          status_approved: "Aprobada",
          status_rejected: "Rechazada",
          rank: "Clasificación",
          view_details: "Ver Detalles",
          view_page: "Ver Página",
          edit_not_available: "La edición no está disponible para este concurso",
          delete_not_available: "La eliminación no está disponible para este concurso",
          delete_confirm_message: "¿Estás seguro de que deseas eliminar esta candidatura? Esta acción no se puede deshacer.",
          details: "Detalles",
          statistics: "Estadísticas",
          total_shares: "Total de compartidos",
          shares_by_platform: "Compartidos por plataforma",
          no_shares: "Aún no hay compartidos",
          contest: "Concurso",
          date: "Fecha",
          media: "Medios",
          no_title: "Sin título",
          user: "Usuario",
          media_alt: "Medio",
          video_alt: "Vídeo"
        },
        participation_form: {
          title: "Participar en el Concurso",
          description: "Selecciona tu mejor foto o video para participar en este concurso",
          edit_title: "Editar un Candidato",
          edit_description: "Actualiza los detalles de tu envío",
          nominate_title: "Nominar un Candidato",
          nominate_description: "Importa tu video desde YouTube o TikTok",
          select_media: "Selecciona tu media",
          drag_drop: "Arrastra y suelta tu archivo aquí",
          file_info: "o haz clic para seleccionar (Imágenes: JPG, PNG, GIF | Videos: MP4, WebM | Máx: 100MB)",
          submit: "Enviar mi candidatura",
          success: "Tu candidatura ha sido enviada exitosamente. Será revisada por nuestro equipo.",
          success_title: "✅ ¡Candidatura enviada exitosamente!",
          success_edit: "Tu candidatura ha sido actualizada exitosamente.",
          already_participating: "ℹ️ Ya tienes una solicitud para este concurso. Solo puedes enviar una solicitud por concurso.",
          edit_participation: "Editar mi solicitud",
          click_add_images: "Haz clic para agregar imágenes",
          preparing: "Preparando...",
          checking_files: "Verificando archivos...",
          uploading: "Cargando...",
          images_format: "Imágenes",
          click_add_video: "Haz clic para agregar un video",
          video_format: "Video",
          cancel: "Cancelar",
          error: {
            no_media_selected: "Por favor selecciona un archivo",
            invalid_file_type: "Tipo de archivo no soportado",
            file_too_large: "El archivo es demasiado grande (máx 100MB)",
            contest_not_found: "Concurso no encontrado",
            submit_error: "Error al enviar la candidatura",
            gender_restriction_male: "Este concurso está reservado solo para participantes masculinos.",
            gender_restriction_female: "Este concurso está reservado solo para participantes femeninas.",
            gender_not_set: "Su perfil no contiene información de género. Por favor complete su perfil para participar en este concurso.",
            already_submitted: "Ya ha enviado una candidatura para este concurso.",
            submission_closed: "Las inscripciones están cerradas para este concurso.",
            deadline_passed: "La fecha límite de envío ha pasado."
          }
        }
      },
      favorites: {
        title: "Mis Favoritos",
        description: "Ver tus concursos y candidatos favoritos",
        contests_tab: "Concursos",
        contestants_tab: "Candidatos",
        no_favorite_contests: "Aún no tienes concursos favoritos",
        no_favorite_contestants: "Aún no tienes candidatos favoritos"
      },
      myhigh5: {
        title: "MyHigh5",
        description: "Los 5 concursantes por los que has votado",
        hint: "Tu primer voto se muestra en la posición 1 y tu voto más reciente en la posición 5. Puedes votar por un máximo de 5 concursantes.",
        no_votes: "Sin votos",
        no_votes_description: "Aún no has votado por ningún concursante. ¡Explora los concursos para votar!",
        explore_contests: "Explorar concursos",
        explore_more: "Explorar más concursos",
        remaining_votes: "Aún puedes votar por {count} concursante(s) más",
        votes_label: "votos",
        hint_dnd: "Arrastra y suelta para reordenar tus votos. El 1º recibe 5 puntos, el 2º 4 puntos, el 3º 3 puntos, el 4º 2 puntos y el 5º 1 punto. Los votos están limitados a 5 por temporada.",
        rank: "Rango",
        points: "Puntos",
        contestant: "Concursante",
        location: "Ubicación",
        total_votes: "Votos totales",
        vote_date: "Fecha del voto",
        order_saved: "¡Orden guardado!",
        order_error: "Error al guardar el orden",
        points_legend: "Sistema de puntos",
        points_label: "puntos",
        active_tab: "Activos",
        history_tab: "Historial",
        no_history: "Sin historial",
        no_history_description: "Aún no tienes historial de votos.",
        inactive: "Finalizado"
      },
      leaderboard: {
        title: "Clasificación de Patrocinadores",
        subtitle: "Los 10 mejores patrocinadores con más referidos directos",
        mfm_subtitle: "Los 10 mejores patrocinadores MFM con más referidos directos que compraron MFM",
        regular_tab: "Clasificación General",
        mfm_tab: "Clasificación MFM",
        referrals: "Referidos",
        benefit: "Beneficio",
        champion: "Campeón",
        no_data: "No se encontraron patrocinadores",
        info_title: "¿Cómo funciona la clasificación?",
        info_description: "La clasificación se basa en el número de referidos directos (nivel 1) que tiene cada patrocinador. Cuantos más referidos directos tengas, mayor será tu posición en la clasificación."
      }
    },
    contestant_detail: {
      about: "Acerca de",
      gallery: "Galería",
      photos: "Fotos",
      images: "Imágenes",
      videos: "Vídeos",
      votes: "Votos",
      rank: "Rango",
      contest_info: "Concurso",
      candidate_info: "Entrada",
      title: "Título",
      participants: "Participantes",
      registered_on: "Registrado el",
      status: "Estado",
      qualified: "✓ Calificado",
      pending: "⏳ Pendiente",
      confirm_vote: "Confirmar tu voto",
      vote_confirmation: "¿Estás seguro de que quieres votar por",
      are_you_sure: "?",
      cancel: "Cancelar",
      vote: "Votar",
      voted: "Votado",
      voting: "Votando...",
      cover_image: "Imagen de portada",
      vote_error: "Error al votar. Por favor, inténtalo de nuevo.",
      vote_success: "¡Has votado con éxito! ✨",
      add_reaction: "Agregar reacción",
      react: "Reaccionar",
      like: "Me gusta",
      love: "Adorado",
      wow: "Wow",
      dislike: "No me gusta",
      vote_history: "Historial de votos",
      no_votes: "Sin votos por el momento",
      voted_for: "Votó por",
      reaction: "Reacción",
      comment: "Comentario",
      date: "Fecha",
      comments: "Comentarios",
      add_comment: "Agregar comentario",
      comment_placeholder: "Escribe tu comentario...",
      comment_on_photo: "Comentar esta foto",
      comment_on_video: "Comentar este vídeo",
      comment_on_contest: "Comentar este concurso",
      no_comments: "Sin comentarios por el momento",
      comment_posted: "¡Comentario publicado con éxito! ✨",
      comment_error: "Error al publicar comentario",
      comments_count: "Comentarios",
      reply: "Responder",
      reply_placeholder: "Escribe tu respuesta...",
      like_comment: "Me gusta",
      media_preview: "Vista previa del medio",
      close: "Cerrar",
      of: "de",
      contestant_label: "Participante",
      nominator_label: "Nominador",
      nominated_for: "Nominado para:",
      contest_rank_label: "Clasificación",
      description_section: "Descripción",
      candidacy_id: "ID de participación",
      season_label: "Temporada",
      entry_fallback_title: "Participación",
      full_description: "Descripción completa"
    },
    kyc: {
      verification_required: "Verificación de Identidad Requerida",
      verification_required_description: "Para participar en concursos y retirar tus ganancias, debes verificar tu identidad.",
      start_verification: "Iniciar Verificación",
      already_verified: "Identidad Verificada",
      already_verified_description: "Tu identidad ha sido verificada con éxito. Ahora puedes disfrutar de todas las funciones.",
      verification_in_progress: "Verificación en Progreso",
      verification_in_progress_description: "Tu solicitud de verificación está siendo procesada. Te notificaremos cuando el proceso esté completo.",
      verification_continue_description: "Tienes una verificación en progreso. Puedes continuarla o actualizar el estado.",
      continue_verification: "Continuar Verificación",
      login_required: "Por favor inicia sesión para continuar",
      init_error: "No se pudo iniciar la verificación",
      max_attempts_reached: "Número máximo de intentos alcanzado",
      max_attempts_description: "Has utilizado todos tus intentos de verificación. Por favor contacta a nuestro soporte para obtener ayuda.",
      max_attempts_can_pay: "Has utilizado tus intentos gratuitos. Puedes comprar intentos adicionales para continuar.",
      buy_attempts: "Comprar intentos adicionales",
      price_per_attempt: "Precio por intento",
      pay_and_retry: "Pagar y reintentar",
      attempts_remaining: "Intentos restantes",
      attempts_used: "Intentos utilizados",
      verification_status: "Estado de Verificación",
      verification_status_description: "Verifica el estado de tu verificación de identidad",
      verification_rejected: "Verificación Rechazada",
      verification_rejected_description: "Tu solicitud de verificación fue rechazada. Puedes enviar una nueva solicitud.",
      rejection_reason: "Motivo del Rechazo",
      submitted_on: "Enviado el",
      submit_again: "Reintentar",
      verification_steps: "¿Cómo funciona?",
      step_1_title: "1. Información Personal",
      step_1_desc: "Proporciona tu información personal básica",
      step_2_title: "2. Documento de Identidad",
      step_2_desc: "Toma una foto de tu documento de identidad",
      step_3_title: "3. Selfie de Verificación",
      step_3_desc: "Toma una selfie para confirmar tu identidad",
      accepted_documents: "Documentos Aceptados",
      doc_passport: "Pasaporte",
      doc_id_card: "Documento de Identidad",
      doc_driving_license: "Licencia de Conducir",
      initiating: "Iniciando...",
      redirect_notice: "Serás redirigido a nuestro socio de verificación seguro",
      follow_instructions: "Sigue las instrucciones a continuación para completar tu verificación de identidad.",
      secure_verification: "Verificación segura por nuestro socio certificado",
      uploaded_documents: "Documentos Cargados",
      document_front: "Frente del Documento",
      document_back: "Reverso del Documento",
      selfie: "Selfie",
      steps: "Pasos de Verificación",
      personal_info: "Información Personal",
      personal_info_desc: "Ingresa tus datos personales",
      document_info: "Información del Documento",
      document_info_desc: "Proporciona los detalles de tu documento",
      review_submit: "Revisar y Enviar",
      review_submit_desc: "Revisa y envía tu información",
      secure: "Tus Datos están Seguros",
      secure_desc: "Toda tu información está encriptada y protegida según los estándares internacionales.",
      first_name: "Nombre",
      first_name_placeholder: "Ingresa tu nombre",
      last_name: "Apellido",
      last_name_placeholder: "Ingresa tu apellido",
      date_of_birth: "Fecha de Nacimiento",
      nationality: "Nacionalidad",
      nationality_placeholder: "Ingresa tu nacionalidad",
      address: "Dirección",
      address_placeholder: "Ingresa tu dirección completa",
      document_type: "Tipo de Documento",
      passport: "Pasaporte",
      national_id: "Cédula de Identidad",
      drivers_license: "Licencia de Conducir",
      document_number: "Número de Documento",
      document_number_placeholder: "Ingresa tu número de documento",
      issuing_country: "País Emisor",
      issuing_country_placeholder: "Ingresa el país que emitió tu documento",
      document_upload_next: "Carga de Documento Próxima",
      document_upload_next_desc: "En el siguiente paso, cargarás fotos de tu documento (frente y reverso) y una selfie.",
      processing_time: "Tiempo de Procesamiento",
      processing_time_desc: "Tu verificación será procesada en 24-48 horas. Recibirás una notificación por correo una vez completada.",
      submission_success: "¡Verificación enviada exitosamente! Redirigiendo...",
      submit_verification: "Enviar Verificación",
      errors: {
        first_name_required: "El nombre es requerido",
        last_name_required: "El apellido es requerido",
        date_of_birth_required: "La fecha de nacimiento es requerida",
        nationality_required: "La nacionalidad es requerida",
        address_required: "La dirección es requerida",
        document_type_required: "El tipo de documento es requerido",
        document_number_required: "El número de documento es requerido",
        issuing_country_required: "El país emisor es requerido",
        document_front_required: "La foto frontal del documento es requerida",
        document_back_required: "La foto trasera del documento es requerida",
        selfie_required: "El selfie es requerido"
      }
    },
    payment: {
      payment_required: "Pago Requerido",
      payment_instructions: "Instrucciones de Pago",
      payment_description: "Para acceder a {product}, realice un pago de {amount}.",
      send_exact_amount: "Envíe exactamente {amount} a la dirección de abajo.",
      kyc_verification: "Verificación KYC",
      efm_membership: "Membresía EFM",
      kyc_description: "Verificación de identidad para participar en concursos",
      efm_description: "Conviértase en miembro fundador EFM",
      validity_one_year: "Validez: 1 año por unidad",
      unit: "unidad",
      quantity: "Cantidad",
      total: "Total",
      choose_method: "Elija su método de pago",
      choose_product: "Elegir un producto",
      choose_product_description: "Seleccione el producto que desea comprar.",
      payment_method: "Método de pago",
      cryptocurrencies: "Criptomonedas",
      other_methods: "Otros métodos",
      card: "Tarjeta bancaria",
      bank_transfer: "Transferencia bancaria",
      network: "Red",
      amount_to_send: "Cantidad a enviar",
      receiving_address: "Dirección de recepción",
      bank_details: "Datos bancarios",
      beneficiary: "Beneficiario",
      bank_reference_info: "Incluya su email como referencia de la transferencia para facilitar la identificación.",
      network_warning: "Asegúrese de enviar la cantidad exacta en la red correcta. Los errores de red pueden resultar en pérdida de fondos.",
      payment_done: "He realizado el pago",
      validation_time_info: "Después de su pago, la validación puede tardar de unos minutos a unas horas según el método elegido.",
      min: "Mín",
      min_amount: "Cantidad mínima",
      min_amount_error: "La cantidad mínima es {amount}",
      enter_amount: "Ingrese la cantidad",
      custom_amount: "Cantidad personalizada",
      card_coming_soon: "Pago con tarjeta próximamente",
      creating_payment: "Creando pago...",
      order_id: "Referencia",
      add_recipients: "Agregar beneficiarios",
      recipients_description: "Agregue los usuarios para los que desea pagar",
      method_description: "Elija su método de pago",
      instructions_description: "Envíe la cantidad exacta a la dirección indicada",
      recipient: "Beneficiario",
      username_or_email: "Nombre de usuario o correo",
      user_not_found: "Usuario no encontrado",
      product_type: "Tipo de producto",
      amount: "Monto",
      min_100: "Mínimo 100 USD",
      add_recipient: "Agregar un beneficiario",
      recipients_count: "beneficiario(s)",
      confirm_close_title: "¿Cerrar pago?",
      confirm_close_description: "Su progreso se perderá. ¿Está seguro de que desea cerrar?",
      pay_for_myself: "Pagar por mí",
      pay_for_others: "Pagar por otros",
      add_other_user: "Agregar otro usuario",
      checking: "Verificando...",
      waiting_confirmation: "Pago en espera de confirmación...",
      not_received: "Pago aún no recibido. Por favor intente de nuevo.",
      success_title: "¡Pago confirmado!",
      success_description: "Su pago ha sido recibido y confirmado. Puede continuar ahora.",
      amount_paid: "Monto pagado",
      auto_checking: "Verificación automática activa",
      last_check: "Última verif.",
      waiting_payment: "Esperando pago...",
      confirming: "Pago detectado, confirmando...",
      partially_paid: "Pago parcial recibido. Por favor complete el monto.",
      kyc_verification: "Servicio KYC",
      mfm_membership: "MFM",
      annual_membership: "Membresía Anual",
      buy_services: "Comprar servicios",
      select_for_myself: "Para mí mismo",
      select_service: "Selecciona un servicio para ti",
      kyc_description: "Verificación de identidad para participar en concursos",
      mfm_description: "Acceso al pool de ingresos mensuales (10%) y anuales (20%) + referidos aleatorios",
      annual_description: "Renovación anual del estatus Founding Member",
      total_to_pay: "Total a pagar",
      card: "Tarjeta de crédito",
      bank_transfer: "Transferencia bancaria",
      no_payment_id: "No se encontró ID de pago",
      payment_expired: "Este pago ha expirado. Por favor cree un nuevo pago.",
      fetch_error: "Error al cargar los detalles del pago"
    },
    contests: {
      profile_incomplete_title: "Perfil incompleto",
      profile_incomplete_message: "Completa tu perfil para poder participar en los concursos.",
      complete_profile: "Completar",
      kyc_required_title: "Verificación de identidad requerida",
      kyc_required_message: "Verifica tu identidad (KYC) para poder participar en los concursos.",
      kyc_recommended_title: "Verificación de identidad recomendada",
      kyc_recommended_message: "Algunos concursos requieren verificación KYC para participar.",
      verify_identity: "Verificar"
    },
    user: {
      profile: "Perfil",
      settings: "Configuración",
      kyc: "Verificación KYC",
      subscription: "Suscripción",
      logout: "Cerrar Sesión"
    },
    notifications: {
      title: "Notificaciones",
      no_notifications: "No hay notificaciones",
      mark_all_read: "Marcar todas como leídas",
      mark_as_read: "Marcar como leída",
      view_all: "Ver todas las notificaciones",
      types: {
        system: "Sistema",
        contest: "Concurso",
        compte: "Cuenta"
      },
      messages: {
        new_vote: "votó por tu candidatura",
        new_comment: "comentó tu candidatura",
        new_reply: "respondió a tu comentario",
        new_like: "le gustó tu comentario",
        new_reaction: "reaccionó a tu candidatura"
      },
      time: {
        just_now: "Ahora mismo",
        seconds_ago: "hace unos segundos",
        minute_ago: "hace un minuto",
        minutes_ago: "hace {count} minutos",
        hour_ago: "hace una hora",
        hours_ago: "hace {count} horas",
        day_ago: "hace un día",
        days_ago: "hace {count} días",
        week_ago: "hace una semana",
        weeks_ago: "hace {count} semanas",
        month_ago: "hace un mes",
        months_ago: "hace {count} meses",
        year_ago: "hace un año",
        years_ago: "hace {count} años"
      }
    },
    pages: {
      contests: {
        badge: "Concursos en curso",
        title: "Descubre Nuestros Concursos",
        subtitle: "Participa, nombra o vota en competiciones emocionantes que progresan del nivel local al nivel global.",
        search_placeholder: "Buscar un concurso...",
        filters: {
          all: "Todos",
          city: "Ciudad",
          country: "País",
          regional: "Regional",
          continental: "Continental",
          global: "Global"
        },
        stats: {
          active: "Concursos activos",
          participants: "Participantes",
          levels: "Niveles"
        },
        all_contests: "Todos los concursos",
        contests_filter: "Concursos",
        results: "resultado",
        reset_filters: "Restablecer filtros",
        join_community: "Únete a la comunidad",
        learn_more: "Saber más",
        no_results: "Ningún concurso encontrado",
        try_different_filter: "Prueba otro filtro o término de búsqueda",
        auth_required_title: "Inicio de sesión requerido",
        auth_required_description: "Debes iniciar sesión para participar en concursos o ver participantes.",
        auth_required_benefits_title: "Al iniciar sesión, podrás:",
        auth_required_benefit_participate: "Participar en concursos",
        auth_required_benefit_view_contestants: "Ver participantes",
        auth_required_benefit_vote: "Votar por tus favoritos",
        auth_required_benefit_comment: "Comentar e interactuar",
        auth_required_login: "Iniciar sesión",
        auth_required_register: "Crear una cuenta",
        cta: {
          title: "¿Listo para participar?",
          subtitle: "¡Crea tu cuenta gratis y comienza a competir hoy!",
          button: "Crear mi cuenta"
        }
      },
      clubs: {
        title: "Fan Clubs Exclusivos",
        subtitle: "Únete a comunidades apasionadas y accede a contenido exclusivo",
        search_placeholder: "Buscar un club...",
        features: {
          dsp: "Pago DSP",
          multi_admin: "Multi-Admin",
          affiliate: "Programa de Afiliados"
        },
        no_results: "Ningún club encontrado",
        try_different_filter: "Prueba otro filtro",
        cta: {
          title: "Crea tu propio Club",
          subtitle: "Monetiza tu contenido, gestiona tu comunidad y gana con el programa de afiliados.",
          feature1: "Pagos seguros vía DSP",
          feature2: "Gestión multi-administrador",
          feature3: "20% de comisión en ventas",
          button: "Crear mi Club"
        }
      },
      about: {
        title: "Sobre MyHigh5",
        subtitle: "La primera plataforma holística de concursos en línea que descubre y muestra talento desde el nivel de ciudad hasta el escenario global.",
        mission: {
          title: "Nuestra Misión",
          description: "Democratizar el acceso a los concursos y permitir que cada talento brille en el escenario mundial."
        },
        values: {
          title: "Nuestros Valores",
          subtitle: "Los principios que guían cada una de nuestras decisiones"
        },
        timeline: {
          title: "Nuestro Recorrido"
        },
        team: {
          title: "Nuestro Equipo",
          subtitle: "Apasionados dedicados a tu éxito"
        },
        cta: {
          title: "Únete a la Aventura MyHigh5",
          subtitle: "Sé parte de una comunidad global de talentos.",
          button: "Comenzar Ahora"
        }
      },
      contact: {
        title: "Contáctanos",
        subtitle: "Nuestro equipo está aquí para ayudarte. Normalmente respondemos en 24 horas.",
        form: {
          title: "Envíanos un mensaje",
          name: "Nombre completo",
          email: "Email",
          category: "Categoría",
          subject: "Asunto",
          message: "Mensaje",
          submit: "Enviar mensaje"
        },
        faq: {
          title: "Preguntas Frecuentes"
        },
        hours: {
          title: "Horario de soporte"
        },
        categories: {
          title: "¿Cómo podemos ayudarte?"
        }
      }
    },
    verification: {
      requirements_title: "Verificaciones Requeridas",
      requirements_description: "Este concurso requiere las siguientes verificaciones para participar.",
      contest: "Concurso",
      progress: "Progreso",
      completed: "Completado",
      required: "Requerido",
      verify: "Verificar",
      proceed: "Continuar",
      incomplete_warning: "Complete todas las verificaciones para participar.",
      kyc_verification: "Verificación KYC",
      visual_verification: "Verificación Visual (Selfie)",
      voice_verification: "Verificación de Voz",
      selfie: "Selfie de Verificación",
      selfie_with_pet: "Selfie con tu mascota",
      selfie_with_document: "Selfie con documento",
      selfie_instructions: "Tome una foto clara de su rostro, bien iluminado.",
      selfie_pet_instructions: "Tome una foto clara de usted con su mascota.",
      selfie_document_instructions: "Tome una foto de usted con un documento de identidad visible.",
      voice_instructions: "Grabe su voz durante unos segundos.",
      use_camera: "Usar cámara",
      upload_image: "Subir imagen",
      camera_error: "No se puede acceder a la cámara",
      microphone_error: "No se puede acceder al micrófono",
      file_too_large: "El archivo es demasiado grande",
      file_too_large_with_size: "El archivo es demasiado grande. Tamaño máximo permitido",
      invalid_file_type: "Tipo de archivo inválido",
      upload_error: "Error al subir",
      capture: "Capturar",
      retake: "Repetir",
      confirm: "Confirmar",
      tap_to_record: "Toque para grabar",
      recording: "Grabando...",
      recording_complete: "Grabación completa",
      play: "Reproducir",
      stop: "Detener",
      selfie_success: "Selfie guardado exitosamente",
      voice_success: "Grabación de voz guardada exitosamente"
    }
  },
  de: {
    not_found: {
      title: "Seite nicht gefunden",
      description: "Entschuldigung, die Seite, die Sie suchen, existiert nicht oder wurde verschoben.",
      go_back: "Zurück",
      go_home: "Startseite",
      quick_links: "Schnelllinks",
      help_text: "Wenn Sie denken, dass dies ein Fehler ist, kontaktieren Sie bitte unseren Support."
    },
    admin: {
      title: "Verwaltungsbereich",
      subtitle: "Verwalten Sie Ihre Plattform",
      nav: {
        main: "Haupt",
        dashboard: "Dashboard",
        management: "Verwaltung",
        seasons: "Jahreszeiten",
        contests: "Wettbewerbe",
        contestants: "Teilnehmer",
        users: "Benutzer",
        kyc: "KYC",
        reports: "Berichte",
        configuration: "Konfiguration",
        categories: "Kategorien",
        commission_settings: "Provisionseinstellungen",
        suggested_contests: "Vorgeschlagene Wettbewerbe",
        transactions: "Transaktionen",
        microservices: "Microservices"
      },
      dashboard: {
        total_seasons: "Gesamte Jahreszeiten",
        active: "aktiv",
        inactive: "inaktiv",
        admins: "Administratoren",
        votes: "Stimmen",
        total_votes: "Gesamte Stimmen",
        comments: "Kommentare",
        total_comments: "Gesamte Kommentare",
        quick_actions: "Schnellaktionen",
        user_progress: "Benutzerfortschritt",
        reports: {
          title: "Berichte",
          description: "Generieren und anzeigen Sie Ihre Berichte",
          financial_report: "Finanzbericht",
          financial_description: "Einnahmen, Ausgaben und Gewinne",
          users_report: "Benutzerbericht",
          users_description: "Statistiken und Fortschritt",
          contests_report: "Wettbewerbsbericht",
          contests_description: "Wettbewerbsleistung",
          votes_report: "Abstimmungsbericht",
          votes_description: "Abstimmungsanalyse",
          recent_reports: "Aktuelle Berichte"
        },
        chart_labels: {
          total_users: "Gesamte Benutzer",
          active_users: "Aktive Benutzer",
          new_users: "Neue Benutzer"
        },
        periods: {
          today: "Heute",
          yesterday: "Gestern",
          week: "Woche",
          month: "Monat",
          year: "Jahr"
        },
        statistics: {
          total_deposits: "Gesamteinzahlungen",
          total_withdrawals: "Gesamtabhebungen",
          verified_users: "Verifizierte Benutzer",
          reports: "Berichte",
          categories: "Kategorien",
          deposits_chart: "Einzahlungsdiagramm",
          withdrawals_chart: "Abhebungsdiagramm",
          categories_chart: "Kategoriestatistiken",
          reports_by_type: "Berichte nach Typ",
          amount_eur: "Betrag ($)",
          deposits_count: "Einzahlungen",
          withdrawals_count: "Abhebungen",
          kyc_verified: "KYC verifiziert",
          reports_count: "Berichte",
          categories_total: "Gesamt",
          amount: "Betrag",
          count: "Anzahl",
          contests: "Wettbewerbe",
          uses: "Verwendungen",
          period: "Zeitraum:",
          custom: "Benutzerdefiniert",
          apply: "Anwenden",
          loading: "Laden...",
          refresh: "Aktualisieren",
          no_data_available: "Keine Daten verfügbar"
        }
      },
      profile: {
        participations: "Teilnahmen",
        total_votes: "Stimmen",
        total_favorites: "Favoriten",
        followers: "Follower",
        following: "Folge ich",
        contestants: "Teilnahmen",
        all_rounds: "Alle",
        no_entries: "Noch keine Teilnahmen",
        verified: "Verifiziert",
        years: "Jahre",
        follow: "Folgen",
        unfollow: "Entfolgen",
        followed: "Du folgst diesem Benutzer",
        unfollowed: "Du folgst diesem Benutzer nicht mehr"
      },
      seasons: {
        title: "Jahreszeiten verwalten",
        description: "Erstellen, bearbeiten und verwalten Sie Wettbewerbsjahreszeiten",
        new_season: "Neue Jahreszeit",
        edit_season: "Jahreszeit bearbeiten",
        create_season: "Jahreszeit erstellen",
        year: "Jahr",
        season_number: "Jahreszeitennummer",
        season_title: "Titel",
        status: "Status",
        start_date: "Startdatum",
        end_date: "Enddatum",
        upload_end_date: "Upload-Ende",
        upcoming: "Bevorstehend",
        upload_phase: "Upload-Phase",
        voting_active: "Abstimmung aktiv",
        voting_ended: "Abstimmung beendet",
        completed: "Abgeschlossen",
        cancelled: "Abgebrochen",
        edit: "Bearbeiten",
        delete: "Löschen",
        cancel: "Abbrechen",
        create: "Erstellen",
        confirm_delete: "Sind Sie sicher, dass Sie diese Jahreszeit löschen möchten?",
        confirm_delete_title: "Jahreszeit löschen",
        confirm_delete_message: "Sind Sie sicher, dass Sie diese Jahreszeit löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden.",
        no_seasons: "Keine Jahreszeiten gefunden. Erstellen Sie Ihre erste Jahreszeit.",
        create_success: "Jahreszeit erfolgreich erstellt",
        update_success: "Jahreszeit erfolgreich aktualisiert",
        delete_success: "Jahreszeit erfolgreich gelöscht",
        load_error: "Fehler beim Laden der Jahreszeiten",
        save_error: "Fehler beim Speichern",
        delete_error: "Fehler beim Löschen",
        level: "Ebene",
        level_city: "Stadt",
        level_country: "Land",
          filter_level: "Stufe",
        level_regional: "Regional",
        level_continent: "Kontinent",
        level_global: "Global",
        level_placeholder: "Eine Ebene auswählen",
        season_title_placeholder: "Z.B: Frühjahr 2024 Saison",
        error_level_exists: "Eine Saison mit der Ebene '{level}' existiert bereits. Es kann nur eine aktive Saison pro Ebene geben.",
        error_invalid_level: "Ungültige Ebene. Gültige Ebenen sind: {levels}",
        contestants_count: "Kandidaten",
        contests_count: "Wettbewerbe"
      },
      contests: {
        title: "Wettbewerbe verwalten",
        description: "Erstellen, bearbeiten und verwalten Sie Wettbewerbe",
        new_contest: "Neuer Wettbewerb",
        edit_contest: "Wettbewerb bearbeiten",
        create_contest: "Wettbewerb erstellen",
        name: "Wettbewerbsname",
        contest_description: "Beschreibung",
        contest_type: "Wettbewerbstyp",
        level: "Ebene",
        city: "Stadt",
        country: "Land",
        region: "Region",
        continent: "Kontinent",
        global: "Global",
        active: "Aktiv",
        inactive: "Inaktiv",
        upload_open: "Upload offen",
        voting_active: "Abstimmung aktiv",
        edit: "Bearbeiten",
        delete: "Löschen",
        cancel: "Abbrechen",
        confirm_delete: "Sind Sie sicher, dass Sie diesen Wettbewerb löschen möchten?",
        image: "Wettbewerbsbild",
        no_contests: "Keine Wettbewerbe gefunden",
        voting_restriction: "Abstimmungsbeschränkung",
        none: "Keine",
        male_only: "Nur Männer",
        female_only: "Nur Frauen",
        geographic: "Geografisch",
        age_restricted: "Altersbeschränkung",
        start_date: "Startdatum",
        end_date: "Enddatum",
        search_placeholder: "Suchen",
        sort: "Sortieren nach",
        create_success: "Wettbewerb erfolgreich erstellt",
        create_error: "Fehler beim Erstellen des Wettbewerbs",
        update_success: "Wettbewerb erfolgreich aktualisiert",
        update_error: "Fehler beim Aktualisieren des Wettbewerbs",
        delete_success: "Wettbewerb erfolgreich gelöscht",
        delete_error: "Fehler beim Löschen des Wettbewerbs",
        sort_date: "Datum (Neueste)",
        sort_name: "Name (A-Z)",
        sort_status: "Status",
        participant_count: "Anzahl der Teilnehmer",
        all_loaded: "Alle Wettbewerbe angezeigt",
        creating: "Wird erstellt...",
        updating: "Wird aktualisiert...",
        candidates: "Teilnehmer",
        confirm_delete_title: "Wettbewerb löschen",
        confirm_delete_message: "Sind Sie sicher, dass Sie diesen Wettbewerb löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden.",
        submission_start: "Einreichungsbeginn",
        submission_end: "Einreichungsende",
        voting_start: "Abstimmungsbeginn",
        voting_end: "Abstimmungsende",
        contest_dates: "Wettbewerbsdaten",
        approved: "Genehmigt",
        rejected: "Abgelehnt",
        filter: "Filtern",
        approve: "Genehmigen",
        reject: "Ablehnen",
        view: "Anzeigen",
        no_kyc: "Keine KYC-Überprüfung",
        verification_score: "Vertrauenswert",
        identity: "Identität",
        document: "Dokument",
        address: "Adresse",
        face: "Gesicht",
        confidence_score: "Punktzahl",
        rejection_reason: "Ablehnungsgrund",
        // Verification form labels
        participant_type: "Teilnehmertyp",
        verification_type: "Verifizierungstyp",
        min_age: "Mindestalter",
        max_age: "Höchstalter",
        requires_kyc: "KYC erforderlich",
        requires_visual: "Visuelle Verif.",
        requires_voice: "Stimm-Verif.",
        requires_brand: "Marken-Verif.",
        requires_content: "Inhalts-Verif.",
        // List stats
        participants: "Teilnehmer",
        pending: "Ausstehend",
        // Media requirements
        media_requirements: "Medienanforderungen",
        requires_video: "Video erforderlich",
        max_videos: "Max Videos",
        video_duration: "Max Dauer (min)",
        min_images: "Min Bilder",
        max_images: "Max Bilder",
        // List translations
        level_city: "Stadt",
        level_country: "Land",
          filter_level: "Stufe",
        level_region: "Region",
        level_continent: "Kontinent",
        level_global: "Global",
        contests_count: "Wettbewerbe",
        active_count: "aktiv",
        result: "Ergebnis",
        results: "Ergebnisse",
        found: "gefunden",
        no_results_for: "Keine Ergebnisse für",
        current_image: "Aktuelles Bild",
        participant_individual: "Einzelperson",
        participant_pet: "Haustier",
        participant_club: "Verein",
        participant_content: "Inhalt",
        kyc_required: "KYC erforderlich",
        kyc_not_required: "Ohne KYC",
        verification_visual: "Visuell",
        verification_voice: "Stimme",
        verification_brand: "Marke",
        verification_content: "Inhalt",
        age_restricted: "Altersbeschränkung",
        years: "Jahre",
        // Form placeholders
        name_placeholder: "Z.B.: Schönheitswettbewerb 2024",
        description_placeholder: "Wettbewerbsbeschreibung",
        type_placeholder: "Z.B.: beauty, handsome",
        // Auto dates
        auto_dates_title: "Automatische Daten",
        auto_dates_description: "Die Daten werden automatisch generiert",
        auto_date_upload_start: "Upload-Start: Erstellungsdatum",
        auto_date_upload_end: "Upload-Ende: 1 Monat nach Start",
        auto_date_vote_start: "Abstimmungsstart: 1 Tag nach Upload-Ende",
        auto_date_vote_end: "Abstimmungsende: 1 Monat nach Abstimmungsstart",
        // Additional form labels
        verification_requirements: "Verifizierungsanforderungen",
        verification_none: "Keine",
        none: "Keine",
        male_only: "Nur Männer",
        female_only: "Nur Frauen",
        geographic: "Geografisch",
        // Additional placeholders
        min_age_placeholder: "Z.B.: 18",
        max_age_placeholder: "Z.B.: 35",
        search_input_placeholder: "Name, Typ, Beschreibung...",
        sort: "Sortieren nach",
        // Season dates
        season_dates: "Saisondaten",
        season_dates_description_edit: "Diese Daten werden automatisch aus dem Abstimmungsstartdatum berechnet. Sie können sie bei Bedarf manuell ändern.",
        season_dates_description_create: "Diese Daten werden beim Erstellen automatisch aus dem Abstimmungsstartdatum berechnet. Sie können sie bei Bedarf vorausfüllen.",
        city_season: "Stadt-Saison",
        country_season: "Land-Saison",
        regional_season: "Regionale Saison",
        continental_season: "Kontinentale Saison",
        global_season: "Globale Saison",
        start_date: "Startdatum",
        end_date: "Enddatum",
        // Voting type translations
        voting_type: "Abstimmungstyp",
        select_voting_type: "Abstimmungstyp auswählen",
        new_voting_type: "Neuer Abstimmungstyp",
        voting_types_load_error: "Fehler beim Laden der Abstimmungstypen",
        voting_type_created: "Abstimmungstyp erfolgreich erstellt",
        voting_type_create_error: "Fehler beim Erstellen des Abstimmungstypen",
        create_voting_type: "Abstimmungstyp erstellen",
        voting_type_name_placeholder: "Z.B.: Stadt-Abstimmung - Werbekommission",
        voting_level: "Abstimmungsniveau",
        commission_source: "Kommissionsquelle",
        commission_rules: "Kommissionsregeln (JSON)",
        commission_rules_help: "Kommissionsregeln sind optional. Format: L1 für Stufe 1, L2-10 für Stufen 2 bis 10.",
        commission_advert: "Werbung",
        commission_affiliate: "Affiliate",
        commission_kyc: "KYC",
        commission_mfm: "MFM",
        create: "Erstellen",
        // Category translations
        category: "Kategorie",
        select_category: "Kategorie auswählen",
        no_category: "Keine Kategorie",
        add_category: "Kategorie hinzufügen",
        create_category: "Kategorie erstellen",
        category_name_required: "Der Kategoriename ist erforderlich",
        category_created: "Kategorie erfolgreich erstellt",
        category_create_error: "Fehler beim Erstellen der Kategorie",
        categories_load_error: "Fehler beim Laden der Kategorien",
        category_name_placeholder: "Z.B.: Pop, Rock, Hip hop",
        slug: "Slug",
        slug_placeholder: "Z.B.: pop, rock, hip-hop",
        slug_help: "Der Slug wird automatisch aus dem Namen generiert. Sie können ihn bei Bedarf ändern.",
        category_description_placeholder: "Kategoriebeschreibung (optional)",
        contest_type_auto_filled: "Der Wettbewerbstyp wird automatisch aus der Kategorie ausgefüllt"
      },
      contestants: {
        title: "Teilnehmer verwalten",
        description: "Genehmigen oder lehnen Sie Bewerbungen ab",
        search_placeholder: "Nach Name oder Titel suchen...",
        all: "Alle",
        pending: "Ausstehend",
        verified: "Verifiziert",
        filter: "Filtern",
        approve: "Genehmigen",
        reject: "Ablehnen",
        view: "Anzeigen",
        author: "Autor",
        images: "Bilder",
        videos: "Videos",
        votes: "Stimmen",
        comments: "Kommentare",
        status: "Status",
        registration_date: "Registrierungsdatum",
        actions: "Aktionen",
        contestant_details: "Teilnehmerdetails",
        close: "Schließen",
        no_contestants: "Keine Teilnehmer gefunden",
        status_pending: "Ausstehend",
        status_verified: "Verifiziert",
        status_rejected: "Abgelehnt",
        approve_success: "Teilnehmer erfolgreich genehmigt",
        approve_error: "Fehler beim Genehmigen des Teilnehmers",
        reject_success: "Teilnehmer erfolgreich abgelehnt",
        reject_error: "Fehler beim Ablehnen des Teilnehmers",
        status_update_success: "Teilnehmerstatus erfolgreich aktualisiert",
        status_update_error: "Fehler beim Aktualisieren des Teilnehmerstatus",
        comment_delete_success: "Kommentar erfolgreich gelöscht",
        comment_delete_error: "Fehler beim Löschen des Kommentars",
        comment_hide_success: "Kommentar erfolgreich ausgeblendet",
        comment_hide_error: "Fehler beim Ausblenden des Kommentars",
        comment_show_success: "Kommentar erfolgreich angezeigt",
        comment_show_error: "Fehler beim Anzeigen des Kommentars",
        comment_restore_success: "Kommentar erfolgreich wiederhergestellt",
        comment_restore_error: "Fehler beim Wiederherstellen des Kommentars",
        new_contestant: "Neuer Teilnehmer",
        edit_contestant: "Teilnehmer bearbeiten",
        user: "Benutzer",
        select_user: "Benutzer auswählen",
        select_season: "Saison auswählen",
        no_seasons_for_level: "Keine Saisons für diese Ebene verfügbar",
        title_placeholder: "Titel des Teilnehmers",
        description_placeholder: "Beschreibung des Teilnehmers",
        create_success: "Teilnehmer erfolgreich erstellt",
        update_success: "Teilnehmer erfolgreich aktualisiert",
        save_error: "Fehler beim Speichern",
        seasons_load_error: "Fehler beim Laden der Saisons",
        no_seasons_available: "Keine Saisons verfügbar. Bitte erstellen Sie zuerst eine Saison."
      },
      categories: {
        title: "Kategorieverwaltung",
        description: "Erstellen und verwalten Sie Wettbewerbskategorien",
        add_category: "Kategorie hinzufügen",
        search_placeholder: "Nach einer Kategorie suchen...",
        no_categories: "Noch keine Kategorien",
        no_categories_found: "Keine Kategorien gefunden",
        created_at: "Erstellt am",
        edit_category: "Kategorie bearbeiten",
        create_category: "Neue Kategorie erstellen",
        edit_category_description: "Kategorieinformationen bearbeiten",
        create_category_description: "Füllen Sie die Informationen aus, um eine neue Kategorie zu erstellen",
        category_name: "Name",
        category_name_required: "Name ist erforderlich",
        category_name_max_length: "Name darf nicht mehr als 100 Zeichen enthalten",
        slug: "Slug",
        slug_required: "Slug ist erforderlich",
        slug_max_length: "Slug darf nicht mehr als 100 Zeichen enthalten",
        slug_invalid: "Slug darf nur Kleinbuchstaben, Zahlen und Bindestriche enthalten",
        slug_auto_generated: "Der Slug wird automatisch aus dem Namen generiert",
        description_label: "Beschreibung",
        description_placeholder: "Kategoriebeschreibung (optional)",
        is_active: "Aktive Kategorie",
        cancel: "Abbrechen",
        save: "Speichern",
        saving: "Speichern...",
        edit: "Bearbeiten",
        create: "Erstellen",
        delete: "Löschen",
        delete_confirm: "Sind Sie sicher, dass Sie die Kategorie löschen möchten",
        category_created: "Kategorie erfolgreich erstellt",
        category_updated: "Kategorie erfolgreich aktualisiert",
        category_deleted: "Kategorie erfolgreich gelöscht",
        category_create_error: "Fehler beim Erstellen der Kategorie",
        category_update_error: "Fehler beim Aktualisieren der Kategorie",
        category_delete_error: "Fehler beim Löschen der Kategorie",
        categories_load_error: "Fehler beim Laden der Kategorien"
      },
      kyc: {
        title: "KYC verwalten",
        description: "Genehmigen oder lehnen Sie Identitätsüberprüfungen ab",
        search_placeholder: "Nach E-Mail oder Name suchen...",
        pending: "Ausstehend",
        approved: "Genehmigt",
        rejected: "Abgelehnt",
        filter: "Filtern",
        approve: "Genehmigen",
        reject: "Ablehnen",
        view: "Details",
        no_kyc: "Keine KYC-Überprüfungen gefunden",
        verification_score: "Vertrauenswert",
        identity: "Identität",
        document: "Dokument",
        address: "Adresse",
        face: "Gesicht",
        confidence_score: "Punktzahl",
        rejection_reason: "Ablehnungsgrund"
      },
      reports: {
        title: "Berichtsverwaltung",
        description: "Verwalten Sie Inhaltsberichte",
        search_placeholder: "Nach einem Bericht suchen...",
        all: "Alle",
        pending: "Ausstehend",
        reviewed: "Überprüft",
        resolved: "Gelöst",
        no_reports: "Noch keine Berichte",
        no_reports_found: "Keine Berichte gefunden",
        report_number: "Bericht #",
        reason: "Grund",
        description_label: "Beschreibung",
        status: "Status",
        details: "Details",
        reported_contestant: "Gemeldeter Teilnehmer",
        contestant_author: "Teilnehmerautor",
        reporter: "Melder",
        contest: "Wettbewerb",
        created_at: "Erstellt am",
        reviewed_at: "Überprüft am",
        moderator_notes: "Moderatornotizen",
        verification_status: "Verifizierungsstatus",
        verification_status_pending: "Ausstehend",
        verification_status_approved: "Genehmigt",
        verification_status_rejected: "Abgelehnt",
        reason_spam: "Spam",
        reason_inappropriate: "Unangemessener Inhalt",
        reason_harassment: "Belästigung",
        reason_fake: "Falsches Konto",
        reason_copyright: "Urheberrechtsverletzung",
        reason_other: "Andere",
        no_title: "Kein Titel",
        load_error: "Fehler beim Laden der Berichte",
        report_details: "Berichtsdetails",
        report_details_description: "Vollständige Informationen über den Bericht",
        reason_label: "Berichtsgrund"
      },
      suggested_contests: {
        title: "Vorgeschlagene Wettbewerbe",
        description: "Verwalten Sie von Benutzern eingereichte Wettbewerbsvorschläge",
        search_placeholder: "Nach einem Vorschlag suchen...",
        all: "Alle",
        pending: "Ausstehend",
        approved: "Genehmigt",
        rejected: "Abgelehnt",
        no_suggestions: "Noch keine Vorschläge",
        no_suggestions_found: "Keine Vorschläge gefunden",
        author: "Autor",
        author_not_available: "Autor nicht verfügbar",
        unknown_date: "Unbekanntes Datum",
        details: "Details",
        contest_suggestion_details: "Details zum Wettbewerbsvorschlag",
        status: "Status",
        category: "Kategorie",
        description: "Beschreibung",
        verified: "Verifiziert",
        dates: "Daten",
        created_at: "Erstellt am",
        updated_at: "Aktualisiert am",
        load_error: "Fehler beim Laden der Vorschläge"
      },
      transactions: {
        title: "Transaktionsverwaltung",
        description: "Alle Transaktionen anzeigen (Einzahlungen, Abhebungen, etc.)",
        search_placeholder: "Nach Referenz, Beschreibung, Benutzer suchen...",
        all_types: "Alle Typen",
        all_statuses: "Alle Status",
        no_transactions: "Noch keine Transaktionen",
        no_transactions_found: "Keine Transaktionen gefunden",
        transaction: "Transaktion",
        transaction_details: "Transaktionsdetails",
        transaction_details_description: "Vollständige Informationen über die Transaktion",
        type: {
          deposit: "Einzahlung",
          withdrawal: "Abhebung",
          entry_fee: "Eintrittsgebühr",
          prize_payout: "Preisauszahlung",
          commission: "Provision",
          refund: "Rückerstattung"
        },
        status: {
          pending: "Ausstehend",
          completed: "Abgeschlossen",
          failed: "Fehlgeschlagen",
          cancelled: "Abgebrochen"
        },
        user: "Benutzer",
        contest: "Wettbewerb",
        payment_method: "Zahlungsmethode",
        product_type: "Produkttyp",
        amount: "Betrag",
        currency: "Währung",
        description: "Beschreibung",
        reference: "Referenz",
        order_id: "Bestell-ID",
        external_payment_id: "Externe Zahlungs-ID",
        tx_hash: "Transaktions-Hash",
        created_at: "Erstellt am",
        processed_at: "Verarbeitet am",
        validated_at: "Validiert am",
        type_label: "Typ",
        status_label: "Status",
        details: "Details",
        search: "Suchen",
        load_error: "Fehler beim Laden der Transaktionen"
      },
      users: {
        title: "Benutzer verwalten",
        description: "Verwalten Sie Benutzerrollen und Berechtigungen",
        search_placeholder: "Nach E-Mail, Name oder Benutzername suchen...",
        all: "Alle",
        admins: "Administratoren",
        verified: "Verifiziert",
        inactive: "Inaktiv",
        filter: "Filtern",
        table_user: "Benutzer",
        table_email: "E-Mail",
        table_participations: "Teilnahmen",
        table_prizes: "Preise",
        table_candidates: "Kandidaten",
        table_contests: "Wettbewerbe",
        table_status: "Status",
        table_actions: "Aktionen",
        make_admin: "Admin machen",
        remove_admin: "Admin entfernen",
        activate: "Aktivieren",
        deactivate: "Deaktivieren",
        no_users: "Keine Benutzer gefunden",
        registered: "Registriert",
        inactive_status: "Inaktiv",
        user: "Benutzer",
        email: "E-Mail",
        participations: "Teilnahmen",
        prizes: "Preise",
        candidates: "Kandidaten",
        contests: "Wettbewerbe",
        status: "Status",
        actions: "Aktionen",
        details: "Details",
        comments: "Kommentare",
        view_comments: "Kommentare anzeigen",
        no_comments: "Keine Kommentare",
        comment_text: "Text",
        comment_date: "Datum",
        comment_author: "Autor",
        city: "Stadt",
        country: "Land",
        continent: "Kontinent",
        region: "Region",
        kyc_status: "KYC-Status",
        kyc_verified: "Verifiziert",
        kyc_pending: "Ausstehend",
        date_of_birth: "Geburtsdatum",
        phone: "Telefon",
        bio: "Biografie",
        last_login: "Letzte Anmeldung",
        joined: "Beigetreten",
        participations_count: "Teilnahmen",
        prizes_count: "Preise",
        contestants_count: "Kandidaten",
        contests_participated: "Wettbewerbe",
        confirm_delete_title: "Benutzer löschen",
        confirm_delete_message: "Sind Sie sicher, dass Sie diesen Benutzer löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden.",
        delete: "Löschen",
        cancel: "Abbrechen",
        delete_success: "Benutzer erfolgreich gelöscht",
        delete_error: "Fehler beim Löschen des Benutzers",
        personal_info: "Persönliche Informationen",
        account_status: "Kontostatus",
        verify_kyc: "KYC verifizieren",
        unverify_kyc: "KYC widerrufen",
        kyc_verify_success: "KYC erfolgreich verifiziert",
        kyc_unverify_success: "KYC-Verifizierung widerrufen",
        toggle_admin_success: "Administratorrechte geändert",
        toggle_admin_error: "Fehler beim Ändern der Benutzerrolle",
        toggle_active_success_deactivate: "Benutzer deaktiviert",
        toggle_active_success_activate: "Benutzer aktiviert",
        toggle_active_error: "Fehler beim Ändern des Benutzerstatus",
        load_error: "Fehler beim Laden von Benutzern",
        load_details_error: "Fehler beim Laden von Details",
        edit_comment: "Bearbeiten",
        delete_comment: "Löschen",
        hide_comment: "Verbergen",
        show_comment: "Anzeigen",
        comment_edit_success: "Kommentar aktualisiert",
        comment_delete_success: "Kommentar gelöscht",
        comment_hide_success: "Kommentar verborgen",
        comment_show_success: "Kommentar angezeigt",
        comment_edit_error: "Fehler beim Aktualisieren des Kommentars",
        comment_delete_error: "Fehler beim Löschen des Kommentars",
        comment_hide_error: "Fehler beim Verbergen des Kommentars",
        comment_show_error: "Fehler beim Anzeigen des Kommentars",
        contest_label: "Wettbewerb",
        contestant_label: "Teilnehmer"
      },
      reports: {
        title: "Meldungen",
        description: "Inhaltsmeldungen verwalten",
        pending: "ausstehend",
        reviewed: "überprüft",
        resolved: "gelöst",
        search_placeholder: "Nach Grund oder Typ suchen...",
        filter: "Filtern",
        all: "Alle",
        no_reports: "Keine Meldungen gefunden",
        reporter: "Melder",
        reported_content: "Gemeldeter Inhalt",
        reason: "Grund",
        status: "Status",
        date: "Datum",
        actions: "Aktionen",
        view: "Anzeigen",
        mark_reviewed: "Als überprüft markieren",
        mark_resolved: "Als gelöst markieren",
        details: "Details",
        close: "Schließen",
        report_details: "Meldungsdetails",
        reported_by: "Gemeldet von",
        reported_at: "Gemeldet am",
        report_reason: "Meldungsgrund",
        report_description: "Beschreibung",
        report_status: "Status",
        moderator_notes: "Moderatornotizen",
        reviewed_by: "Überprüft von",
        reviewed_at: "Überprüft am",
        content_type: "Inhaltstyp",
        contestant: "Teilnehmer",
        comment: "Kommentar",
        media: "Medien",
        user: "Benutzer",
        mark_reviewed_success: "Meldung als überprüft markiert",
        mark_reviewed_error: "Fehler beim Aktualisieren der Meldung",
        mark_resolved_success: "Meldung als gelöst markiert",
        mark_resolved_error: "Fehler beim Aktualisieren der Meldung",
        load_error: "Fehler beim Laden der Meldungen"
      }
    },
    hero: {
      badge: "Weltweit #1 Wettbewerbsplattform",
      title_line1: "Treten Sie der größten",
      title_line2: "Wettbewerbs-Community",
      title_line3: "der Welt bei",
      description: "Nehmen Sie als Teilnehmer teil, nominieren Sie Ihren Lieblingsteilnehmer in Ihrem Land, oder stimmen Sie bei jedem Wettbewerb ab, und werden Sie belohnt, während Sie Spaß haben.",
      subtitle: "Nehmen Sie als Teilnehmer teil, nominieren Sie Ihren Lieblingsteilnehmer in Ihrem Land, oder stimmen Sie bei jedem Wettbewerb ab, und werden Sie belohnt, während Sie Spaß haben.",
      cta: "Jetzt Loslegen",
      demo: "Demo Ansehen",
      stats: {
        participants: "Aktive Teilnehmer",
        contests: "Organisierte Wettbewerbe",
        countries: "Vertretene Länder"
      },
      trust: {
        secure: "Sicher und zertifiziert",
        support: "24/7 Support",
        free: "Kostenlos beitreten"
      }
    },
    nav: {
      home: "Startseite",
      contests: "Wettbewerbe",
      rankings: "Rankings",
      community: "Community",
      about: "Über uns",
      login: "Anmelden",
      register: "Registrieren"
    },
    navigation: {
      home: "Startseite",
      landing: "Startseite",
      dashboard: "Dashboard",
      contests: "Wettbewerbe",
      clubs: "Clubs",
      about: "Über uns",
      contact: "Kontakt",
      login: "Anmelden",
      register: "Registrieren",
      download_app: "App herunterladen"
    },
    header: {
      language: "Sprache",
      theme: "Design"
    },
    auth: {
      email: "E-Mail",
      password: "Passwort",
      username: "Benutzername",
      forgotPassword: "Passwort vergessen?",
      loginError: "Anmeldefehler",
      registerError: "Registrierungsfehler",
      referral_detected: "Empfehlungscode erkannt!",
      referral_bonus: "Sie wurden empfohlen!",
      referral_code: "Code",
      login: {
        title: "Anmelden",
        subtitle: "Melden Sie sich bei Ihrem MyHigh5-Konto an",
        email_placeholder: "E-Mail oder Benutzername",
        password_placeholder: "Ihr Passwort",
        forgot_password: "Passwort vergessen?",
        loading: "Anmelden...",
        submit: "Anmelden",
        no_account: "Noch kein Konto?",
        register_link: "Registrieren",
        errors: {
          required_fields: "Alle Felder sind erforderlich",
          invalid_credentials: "Ungültige E-Mail/Benutzername oder Passwort",
          timeout: "Zeitüberschreitung. Bitte versuchen Sie es erneut.",
          network_error: "Verbindungsfehler. Bitte überprüfen Sie Ihre Internetverbindung.",
          service_unavailable: "Der Dienst startet. Bitte warten Sie einen Moment und versuchen Sie es erneut."
        }
      },
      register: {
        title: "Registrieren",
        subtitle: "Erstellen Sie Ihr kostenloses MyHigh5-Konto",
        email_placeholder: "Ihre E-Mail-Adresse",
        username_placeholder: "Benutzername",
        username_hint: "Nur Buchstaben, Zahlen und Unterstriche sind erlaubt",
        username_no_spaces_warning: "Ungültige Zeichen",
        username_space_not_allowed: "Leerzeichen sind nicht erlaubt",
        password_requirements_title: "Das Passwort muss enthalten:",
        password_requirement_length: "Mindestens 8 Zeichen",
        password_requirement_uppercase: "Einen Großbuchstaben (A-Z)",
        password_requirement_lowercase: "Einen Kleinbuchstaben (a-z)",
        password_requirement_number: "Eine Zahl (0-9)",
        password_requirement_special: "Ein Sonderzeichen (*_/@=)",
        password_placeholder: "Passwort",
        confirm_password_placeholder: "Passwort bestätigen",
        full_name_placeholder: "Vollständiger Name",
        phone_placeholder: "Telefonnummer",
        referral_code_placeholder: "Empfehlungscode (optional)",
        country: "Land",
        country_placeholder: "Wählen Sie ein Land",
        city: "Stadt",
        city_placeholder: "Geben Sie Ihre Stadt ein",
        loading: "Konto erstellen...",
        submit: "Konto erstellen",
        have_account: "Bereits ein Konto?",
        login_link: "Anmelden",
        terms_accept: "Ich akzeptiere die Nutzungsbedingungen",
        success_title: "Registrierung erfolgreich!",
        success_message: "Willkommen! Ihr Konto wurde erfolgreich erstellt.",
        continue_button: "Anmelden",
        errors: {
          required_fields: "Alle erforderlichen Felder müssen ausgefüllt werden",
          password_mismatch: "Passwörter stimmen nicht überein",
          password_min_length: "Das Passwort muss mindestens 8 Zeichen lang sein",
          terms_required: "Sie müssen den Nutzungsbedingungen zustimmen",
          email_exists: "Ein Benutzer mit dieser E-Mail existiert bereits",
          username_exists: "Dieser Benutzername ist bereits vergeben",
          invalid_email: "Ungültiges E-Mail-Format",
          username_invalid_chars: "Nur Buchstaben, Zahlen und Unterstriche sind erlaubt",
          password_requirements: "Das Passwort muss einen Großbuchstaben, einen Kleinbuchstaben, eine Zahl und ein Sonderzeichen (*_/@=) enthalten",
          location_required: "Bitte wählen Sie Ihr Land und Ihre Stadt aus"
        }
      }
    },
    common: {
      loading: "Wird geladen...",
      error: "Fehler",
      success: "Erfolg",
      network_error: "Verbindungsfehler. Bitte überprüfen Sie Ihre Internetverbindung.",
      cancel: "Abbrechen",
      confirm: "Bestätigen",
      continue: "Fortfahren",
      or: "Oder",
      redirecting: "Anmeldung erfolgreich! Wird zum Dashboard weitergeleitet...",
      please_wait: "Bitte warten",
      back: "Zurück",
      back_to_dashboard: "Zurück zum Dashboard",
      previous: "Zurück",
      next: "Weiter",
      submitting: "Wird eingereicht...",
      no_documents: "Keine Dokumente hochgeladen",
      profile_setup: "Profilkonfiguration",
      profile_setup_description: "Vervollständigen Sie Ihr Profil, um an Wettbewerben teilzunehmen",
      edit: "Bearbeiten",
      delete: "Löschen",
      deleting: "Wird gelöscht...",
      confirm_delete: "Löschung bestätigen",
      deleted_successfully: "Erfolgreich gelöscht",
      likes: "Likes",
      comments: "Kommentare",
      search: "Suchen",
      clear: "Löschen",
      optional: "optional",
      coming_soon: "Demnächst",
      welcome: "Willkommen",
      access_denied: "Zugriff verweigert",
      no_permission: "Sie haben keine Berechtigung, auf diese Seite zuzugreifen.",
      refresh: "Aktualisieren",
      view_more: "Mehr anzeigen",
      unknown: "Unbekannt",
      load_more: "Mehr laden",
      actions: "Aktionen"
    },
    affiliates: {
      grow_network: "Bauen Sie Ihr Netzwerk aus",
      invite_friends: "Laden Sie Freunde ein und verdienen Sie Provisionen für ihre Aktivitäten",
      invite_now: "Jetzt Einladen",
      title: "Partnerprogramm",
      your_link: "Ihr Partner-Link",
      copy_link: "Link Kopieren",
      link_copied: "Link kopiert!",
      share: "Teilen",
      earnings: "Ihre Einnahmen",
      pending: "Ausstehend",
      paid: "Bezahlt",
      referrals: "Empfehlungen",
    },
    profile_setup: {
      location: "Standort",
      gender: "Geschlecht",
      date_of_birth: "Geburtsdatum",
      male: "Männlich",
      female: "Weiblich",
      other: "Sonstiges",
      prefer_not_to_say: "Möchte nicht angeben",
      first_name: "Vorname",
      first_name_placeholder: "Dein Vorname",
      first_name_required: "Vorname ist erforderlich",
      last_name: "Nachname",
      last_name_placeholder: "Dein Nachname",
      last_name_required: "Nachname ist erforderlich",
      avatar: "Avatar",
      avatar_required: "Avatar ist erforderlich",
      bio: "Bio",
      bio_placeholder: "Erzähle uns von dir...",
      bio_required: "Bio ist erforderlich",
      characters: "Zeichen",
      city_required: "Stadt ist erforderlich",
      continent_required: "Kontinent ist erforderlich",
      region_required: "Region ist erforderlich",
      country_required: "Land ist erforderlich",
      gender_required: "Geschlecht ist erforderlich",
      dob_required: "Geburtsdatum ist erforderlich",
      session_expired: "Sitzung abgelaufen",
      update_error: "Fehler beim Aktualisieren des Profils",
      success: "Profil erfolgreich konfiguriert!",
      continue: "Fortfahren",
      info: "Diese Informationen sind erforderlich, um an Wettbewerben teilzunehmen. Sie können diese später in Ihren Profileinstellungen ändern.",
      click_upload: "Klicken zum Hochladen",
      preparing: "Vorbereitung...",
      checking_files: "Dateien werden überprüft...",
      uploading: "Wird hochgeladen...",
      images: "Bilder",
      upload_error: "Upload-Fehler"
    },
    settings: {
      title: "Einstellungen",
      description: "Verwalten Sie Ihre persönlichen Informationen und Vorlieben",
      profile: "Profil",
      profile_short: "Foto, Name und Bio",
      profile_description: "Bearbeiten Sie Ihr Foto, Namen und Biografie",
      location: "Standort",
      location_short: "Land und Stadt",
      location_description: "Legen Sie Ihren geografischen Standort fest",
      demographics: "Identität",
      demographics_short: "Geschlecht und Alter",
      demographics_description: "Geben Sie Ihre persönlichen Informationen ein",
      continent: "Kontinent",
      region: "Region",
      country: "Land",
      city: "Stadt",
      current_location: "Aktueller Standort",
      location_locked_title: "Standort Gesperrt",
      location_locked_message: "Sie haben bereits an einem Wettbewerb teilgenommen. Ihr Standort kann nicht geändert werden.",
      save: "Speichern",
      remove: "Löschen",
      profile_completion: "Profil abgeschlossen",
      missing: "Fehlt",
      referral_code_label: "Empfehlungscode",
      admin: "Admin",
      verified: "Verifiziert",
      verify_identity: "Meine Identität verifizieren",
      years: "Jahre",
      user: "Benutzer",
      profile_photo: "Profilfoto",
      biography: "Biografie",
      password: {
        title: "Passwort",
        description: "Ändern Sie Ihr Passwort, um Ihr Konto zu sichern",
        current: "Aktuelles Passwort",
        new: "Neues Passwort",
        confirm: "Neues Passwort bestätigen",
        current_required: "Aktuelles Passwort ist erforderlich",
        new_required: "Neues Passwort ist erforderlich",
        confirm_required: "Passwortbestätigung ist erforderlich",
        min_length: "Passwort muss mindestens 6 Zeichen haben",
        mismatch: "Passwörter stimmen nicht überein",
        same_password: "Neues Passwort muss sich vom alten unterscheiden",
        session_expired: "Sitzung abgelaufen",
        success: "Passwort erfolgreich geändert",
        error: "Fehler beim Ändern des Passworts",
        saving: "Speichern...",
        save: "Passwort ändern",
        security_info: "Kontosicherheit",
        security_description: "Verwenden Sie ein starkes und einzigartiges Passwort, um Ihr Konto zu schützen.",
        min_6_chars: "Mindestens 6 Zeichen",
        uppercase: "Ein Großbuchstabe",
        lowercase: "Ein Kleinbuchstabe",
        number: "Eine Zahl"
      },
      password_short: "Kontosicherheit"
    },
    participation: {
      location: "Ihr Standort",
      category: "Kategorie",
      categoryPlaceholder: "Wählen Sie eine Kategorie",
      title: "Titel",
      title_placeholder: "Geben Sie den Titel Ihres Eintrags ein",
      description: "Beschreibung",
      descriptionPlaceholder: "Beschreiben Sie Ihren Eintrag, Talente, Leistungen...",
      characters: "Zeichen",
      media: "Medien (Bilder/Videos)",
      images: "Bilder",
      images_placeholder: "Klicken Sie, um Bilder hinzuzufügen",
      video: "Video",
      video_placeholder: "Klicken Sie, um ein Video hinzuzufügen",
      video_optional: "Video (optional)",
      clickUpload: "Klicken oder ziehen Sie Ihre Dateien",
      preparing: "Vorbereitung...",
      checkingFiles: "Dateien werden überprüft...",
      uploading: "Wird hochgeladen...",
      imagesVideos: "Bilder und Videos",
      uploadError: "Upload-Fehler",
      uploadedFiles: "Hochgeladene Dateien",
      submit: "Meinen Eintrag einreichen",
      cancel: "Abbrechen",
      profile_incomplete_title: "⚠️ Unvollständiges Profil",
      profile_incomplete_message: "Sie müssen Ihr Profil ausfüllen, bevor Sie an Wettbewerben teilnehmen können. Bitte geben Sie Ihren Vornamen, Nachnamen, Land und Stadt an.",
      complete_profile_button: "Mein Profil Ausfüllen",
      kyc_notification: "⚠️ Ihre Identität wurde nicht überprüft. Wir empfehlen Ihnen, Ihre KYC-Überprüfung abzuschließen, um ein besseres Erlebnis zu haben.",
      // URL import
      or: "oder",
      add_by_url: "Per URL hinzufügen",
      add_video_by_url: "Per URL hinzufügen",
      add: "Hinzufügen",
      image_url_placeholder: "https://beispiel.com/bild.jpg",
      video_url_placeholder: "https://youtube.com/watch?v=... oder https://beispiel.com/video.mp4",
      invalid_video_url: "Nicht autorisierter Link. Nur YouTube und TikTok werden akzeptiert.",
      unsupported_platform: "Nicht autorisierter Link",
      open_link: "Link öffnen",
      view_on_tiktok: "Auf TikTok ansehen",
      view_on_youtube: "Auf YouTube ansehen",
      only_youtube_tiktok: "Nur YouTube und TikTok werden akzeptiert",
      invalid_url: "Ungültige Video-URL",
      video_platform_not_allowed: "Diese Videoplattform wird nicht akzeptiert. Nur YouTube und TikTok werden unterstützt.",
      video_file_not_allowed: "Das Hochladen von Videodateien ist für Nominierungen nicht erlaubt. Bitte verwenden Sie eine YouTube-URL (einschließlich YouTube Shorts), TikTok oder einen anderen Video-Link.",
      youtube_shorts_not_allowed: "YouTube Shorts sind nicht erlaubt. Bitte verwenden Sie ein Standard-YouTube-Video.",
      tiktok_preview_unavailable: "Vorschau nicht verfügbar — auf TikTok ansehen",
      watch_on_tiktok: "Auf TikTok ansehen",
      url_required: "URL erforderlich",
      invalid_url: "Ungültige URL",
      max_images_reached: "Maximale Anzahl an Bildern erreicht",
      image_added: "Bild hinzugefügt",
      video_added: "Video hinzugefügt",
      // Media requirements
      media_requirements: "Medienanforderungen",
      images_required: "Bilder",
      video_required: "Video erforderlich",
      video_required_title: "Video *",
      // New labels
      content_title: "Inhaltstitel",
      content_title_placeholder: "Geben Sie den Inhaltstitel ein (mindestens 10 Zeichen)",
      content_description: "Inhaltsbeschreibung",
      content_description_placeholder: "Geben Sie die Inhaltsbeschreibung ein (20-50 Zeichen)",
      content_image: "Inhaltsbild",
      content_video_required: "Inhaltsvideo *",
      content_video_optional: "Inhaltsvideo (optional)",
      min_characters: "Minimum",
      important_errors: "Wichtige Fehler zu Beheben",
      // Nominator location fields
      nominator_location: "Standort des Kandidaten",
      nominator_location_description: "Bitte geben Sie den Standort der Person an, die Sie nominieren.",
      nominator_country: "Land",
      nominator_country_note: "Das Land muss mit Ihrem Profilland übereinstimmen. Sie können nur Kandidaten aus Ihrem eigenen Land nominieren.",
      select_country: "Land auswählen",
      nominator_city: "Stadt",
      nominator_city_placeholder: "Geben Sie den Stadtnamen ein",
      select_city: "Stadt auswählen",
      select_country_first: "Wählen Sie zuerst ein Land",
      ad_revenue_warning: "Warnung: Sie werden nicht für Werbeeinnahmen bezahlt, die durch Ihren Inhalt generiert werden, wenn wir feststellen, dass der Inhalt nicht aus Ihrem Land stammt.",
      // Errors
      
      // Stepper
      step_info: "Informationen",
      step_media: "Medien",
      step_review: "Überprüfung",
      time_remaining: "Verbleibende Teilnahmezeit",
      deadline: "Frist",
      submission_period_ended: "Die Einreichungsfrist ist abgelaufen",
      review_title: "Überprüfen Sie Ihre Bewerbung",
      supported_platforms: "Unterstützte Plattformen",
      unrecognized_video_link: "Nicht erkannter Videolink",
      errors: {
        content_title_required: "Inhaltstitel",
        content_title_min_length: "Der Inhaltstitel muss mindestens 5 Zeichen enthalten",
        content_title_max_length: "Der Inhaltstitel darf nicht mehr als 5 Zeichen enthalten",
        content_description_required: "Inhaltsbeschreibung",
        content_description_min_length: "Die Inhaltsbeschreibung muss mindestens 20 Zeichen enthalten",
        content_description_max_length: "Die Inhaltsbeschreibung darf nicht mehr als 50 Zeichen enthalten",
        content_image_required: "Inhaltsbild",
        at_least_one_image: "Mindestens ein Bild ist erforderlich",
        content_video_required: "Inhaltsvideo",
        video_required_for_contest: "Ein Video ist für diesen Wettbewerb erforderlich",
        fill_all_fields: "Bitte füllen Sie alle erforderlichen Felder aus, bevor Sie absenden",
        nominator_country_required: "Das Land ist erforderlich"
      }
    },
    moderation: {
      content_rejected: "⚠️ Inhalt durch Moderation abgelehnt",
      adult_content: "Erwachseneninhalt erkannt",
      violence_detected: "Gewaltsamer Inhalt erkannt",
      gore_detected: "Gore/blutiger Inhalt erkannt",
      weapons_detected: "Waffe erkannt",
      offensive_content: "Beleidigender Inhalt erkannt",
      ownership_failed: "Eigentumsüberprüfung fehlgeschlagen",
      face_mismatch: "Gesicht stimmt nicht mit Ihrer Verifizierung überein",
      analyzing: "Inhalt wird analysiert...",
      approved: "Inhalt genehmigt",
      rejected: "Inhalt abgelehnt"
    },
    features: {
      title: "Außergewöhnliche Funktionen",
      subtitle: "Entdecken Sie alles, was MyHigh5 zu einer einzigartigen und aufregenden globalen Online-Wettbewerbsplattform macht.",
      items: {
        multi_level: {
          title: "Mehrstufige Wettbewerbe",
          description: "Nehmen Sie an lokalen, nationalen und internationalen Wettbewerben mit einem einzigartigen Fortschrittssystem teil."
        },
        financial_rewards: {
          title: "Finanzielle Belohnungen",
          description: "Erhalten Sie Affiliate-Provisionen aus den Einnahmen Ihres Empfehlungsnetzwerks, bis zu 10 Generationen tief."
        },
        international_reach: {
          title: "Internationale Reichweite",
          description: "Ihre Talente können von einem vielfältigen globalen Publikum entdeckt und geschätzt werden."
        },
        innovative_voting: {
          title: "Innovatives Abstimmen",
          description: "Faires und transparentes Abstimmungssystem mit Echtzeit-Rankings."
        },
        varied_categories: {
          title: "Vielfältige Kategorien",
          description: "Finden Sie die Wettbewerbskategorien, die Sie zur Teilnahme begeistern. Empfehlen Sie fehlende Kategorien, die Sie gerne hinzugefügt sehen würden."
        }
      }
    },
    testimonials: {
      title: "Was unsere Benutzer sagen",
      favorites: {
        title: "Meine Favoriten",
        description: "Sehen Sie Ihre Lieblingswettbewerbe und Kandidaten an",
        contests_tab: "Wettbewerbe",
        contestants_tab: "Kandidaten",
        no_favorite_contests: "Sie haben noch keine Lieblingswettbewerbe",
        no_favorite_contestants: "Sie haben noch keine Lieblingskandidaten"
      },
      myhigh5: {
        title: "MyHigh5",
        description: "Die 5 Teilnehmer, für die Sie gestimmt haben",
        hint: "Ihre erste Stimme wird an Position 1 angezeigt und Ihre neueste Stimme an Position 5. Sie können für maximal 5 Teilnehmer abstimmen.",
        no_votes: "Keine Stimmen",
        no_votes_description: "Sie haben noch für keine Teilnehmer gestimmt. Erkunden Sie Wettbewerbe, um abzustimmen!",
        explore_contests: "Wettbewerbe erkunden",
        explore_more: "Mehr Wettbewerbe erkunden",
        remaining_votes: "Sie können noch für {count} weitere(n) Teilnehmer abstimmen",
        votes_label: "Stimmen",
        hint_dnd: "Ziehen und ablegen, um Ihre Stimmen neu zu ordnen. Der 1. erhält 5 Punkte, der 2. 4 Punkte, der 3. 3 Punkte, der 4. 2 Punkte und der 5. 1 Punkt. Die Stimmen sind auf 5 pro Saison begrenzt.",
        rank: "Rang",
        points: "Punkte",
        contestant: "Teilnehmer",
        location: "Standort",
        total_votes: "Gesamtstimmen",
        vote_date: "Abstimmungsdatum",
        order_saved: "Reihenfolge gespeichert!",
        order_error: "Fehler beim Speichern",
        points_legend: "Punktesystem",
        points_label: "Punkte"
      },
      subtitle: "Schließen Sie sich Tausenden zufriedener Teilnehmer an, die ihre Leidenschaft in Erfolg verwandelt haben.",
      cta: "Schließen Sie sich Tausenden zufriedener Teilnehmer an",
      users: "+1M Benutzer",
      items: {
        marie: {
          name: "Marie Dubois",
          text: "MyHigh5 ermöglichte es mir, mein Talent zu entdecken und eine unglaubliche Gemeinschaft kennenzulernen. Ich habe dieses Jahr 3 Wettbewerbe gewonnen!",
          role: "Schönheitswettbewerb Gewinnerin",
          rating: 5,
          location: "Paris, Frankreich"
        },
        jean: {
          name: "Jean Martin",
          text: "Die Benutzeroberfläche ist intuitiv und die Wettbewerbe sind vielfältig. Es ist meine Lieblingsplattform geworden, um meine Kreativität auszudrücken.",
          role: "Aktiver Teilnehmer",
          rating: 5,
          location: "Lyon, Frankreich"
        },
        sophie: {
          name: "Sophie Laurent",
          text: "Dank des Partnerprogramms habe ich eine zusätzliche Einkommensquelle geschaffen, während ich Spaß hatte.",
          role: "MyHigh5 Botschafterin",
          rating: 5,
          location: "Marseille, Frankreich"
        },
        sarah_m: {
          name: "Sarah Martin",
          text: "Eine unglaubliche Erfahrung! Ich entdeckte meine Leidenschaft für Fotografie durch MyHigh5-Wettbewerbe.",
          role: "Amateur-Fotografin",
          rating: 5,
          location: "Berlin, Deutschland"
        },
        carlos_r: {
          name: "Carlos Rodriguez",
          text: "Die Gemeinschaft ist fantastisch und sehr ermutigend. Meine Tanztalente wurden international anerkannt!",
          role: "Professioneller Tänzer",
          rating: 5,
          location: "Madrid, Spanien"
        },
        emma_l: {
          name: "Emma Laurent",
          text: "MyHigh5 gab mir das Vertrauen, meine Kreationen zu teilen. Jetzt habe ich meinen eigenen Online-Shop!",
          role: "Kreative Künstlerin",
          rating: 5,
          location: "Brüssel, Belgien"
        }
      }
    },
    cta: {
      title: "Bereit, Ihr Abenteuer zu beginnen?",
      subtitle: "Schließen Sie sich Millionen von Teilnehmern an und entdecken Sie heute Ihr Potenzial.",
      button: "Mein kostenloses Konto erstellen",
      features: {
        instant: "Sofortige Registrierung",
        global: "Globale Gemeinschaft",
        secure: "100% sicher",
        free_contests: "Kostenlose Wettbewerbe",
        active_community: "Aktive Gemeinschaft",
        real_rewards: "Echte Belohnungen"
      },
      trust: {
        instant: "Registrierung in 30 Sekunden",
        secure: "Keine Kreditkarte erforderlich",
        support: "24/7 Support"
      }
    },
    landing: {
      ways_to_earn: {
        badge: "Geld verdienen",
        title: "Verschiedene Möglichkeiten zu verdienen",
        subtitle: "Treten Sie unserem Affiliate-Programm bei und verdienen Sie Provisionen aus mehreren Einnahmequellen",
        kyc_payments: {
          title: "KYC-Zahlungen",
          description: "Verdienen Sie Provisionen, wenn Mitglieder in Ihrem Netzwerk ihre KYC-Verifizierung abschließen",
          commission: "10% auf Stufe 1, 1% auf Stufen 2-10"
        },
        founding_membership: {
          title: "Gründungsmitgliedschaft",
          description: "Verdienen Sie Provisionen, wenn Mitglieder in Ihrem Empfehlungsnetzwerk dem Gründungsmitglieder-Club beitreten oder die jährliche Mitgliedsgebühr zahlen.",
          commission: "10% auf Stufe 1, 1% auf Stufen 2-10"
        },
        annual_membership: {
          title: "Jährliche Mitgliedsgebühr",
          description: "Verdienen Sie Provisionen, wenn Gründungsmitglieder ihre jährliche Mitgliedsgebühr zahlen.",
          commission: "10% auf Stufe 1, 1% auf Stufen 2-10"
        },
        club_memberships: {
          title: "Club-Mitgliedschaften",
          description: "Verdienen Sie Provisionen auf bezahlte Club-Mitgliedsgebühren. Die Website fügt einen Aufschlag von 20% zu den vom Clubeigentümer festgelegten Gebühren hinzu, wovon 10% an Stufe 1 und 1% an jede der Stufen 2 bis 10 gezahlt werden.",
          commission: "10% auf Stufe 1, 1% auf Stufen 2-10"
        },
        shop_purchases: {
          title: "Einkäufe im Shop",
          description: "Verdienen Sie Provisionen auf digitale Inhaltskäufe im MyHigh5-Shop. Die Website fügt einen Aufschlag von 20% zu den vom Clubeigentümer festgelegten Gebühren hinzu, wovon 10% an Stufe 1 und 1% an jede der Stufen 2 bis 10 gezahlt werden.",
          commission: "10% auf Stufe 1, 1% auf Stufen 2-10"
        },
        ad_revenue: {
          title: "Werbeeinnahmen teilen",
          description: "Wettbewerbsteilnehmer verdienen 40% der Werbeeinnahmen, die auf ihren Wettbewerbsseiten generiert werden. Ihre Stufe-1-Patrone verdienen 5%, und die Stufen 2 bis 10 verdienen jeweils 1%. Mitglieder, die Kandidaten nominieren, verdienen 10% der Werbeeinnahmen, die von ihren nominierten Kandidaten generiert werden. Ihre Stufe-1-Patrone verdienen 2.5%, und die Stufen 2 bis 10 verdienen jeweils 1%.",
          commission: "Teilnehmer: 40% für sich selbst, 5% für Stufe 1, 1% für jede der Stufen 2 bis 10.\nNominatoren: 10% für sich selbst, 2.5% für Stufe 1, 1% für jede der Stufen 2 bis 10."
        },
        ad_campaigns: {
          title: "Website-Sponsoren-Seite",
          description: "Stufe-1-Patrone verdienen eine Provision von 10%, und die Stufen 2 bis 10 verdienen jeweils 1%.",
          commission: "10% auf Stufe 1, 1% auf Stufen 2-10"
        }
      },
      faq: {
        badge: "Häufig gestellte Fragen",
        title: "Häufig gestellte Fragen",
        subtitle: "Finden Sie Antworten auf die häufigsten Fragen zu MyHigh5",
        question_1: "Wie kann ich bei MyHigh5 Geld verdienen?",
        answer_1: "Sie können auf verschiedene Weise Geld verdienen: durch Teilnahme an Wettbewerben, durch Nominieren von Kandidaten, durch Beitritt zum Affiliate-Programm, um Provisionen für Mitglieder zu verdienen, die Sie werben, und durch Gründungsmitgliedschaft, um an Einnahme- und Gewinnpools teilzunehmen.",
        question_2: "Wie funktioniert das Affiliate-Programm?",
        answer_2: "• Verifizierungsgebührenzahlungen:\n  Sie verdienen eine Provision von 10% auf Zahlungen, die von Ihren direkten Empfehlungen getätigt werden, und eine Provision von 1% auf Zahlungen, die von jeder Ihrer indirekten Empfehlungen von Stufe 2 bis Stufe 10 getätigt werden.\n\n• Werbeeinnahmen (Teilnehmende Kandidaten):\n  Teilnehmende Kandidaten erhalten 40% der Werbeeinnahmen, die auf ihren Wettbewerbsseiten generiert werden. Der direkte Patron eines teilnehmenden Kandidaten erhält 5%, und jeder indirekte Patron von Stufe 2 bis Stufe 10 erhält 1%.\n\n• Werbeeinnahmen (Nominierende Mitglieder):\n  Nominierende Mitglieder erhalten 10% der Werbeeinnahmen, die auf den Wettbewerbsseiten ihrer nominierten Kandidaten generiert werden, 2.5% der Werbeeinnahmen, die auf den Wettbewerbsseiten von Kandidaten generiert werden, die von ihren direkten Empfehlungen nominiert wurden, und 1% der Werbeeinnahmen, die auf den Wettbewerbsseiten von Kandidaten generiert werden, die von jeder ihrer indirekten Empfehlungen von Stufe 2 bis Stufe 10 nominiert wurden.\n\n• Werbeeinnahmen (Clubs):\n  Clubeigentümer erhalten 20% der Werbeeinnahmen, die auf ihren Club- oder Fan-Seiten generiert werden. Der direkte Patron eines Clubeigentümers erhält 5%, und jeder indirekte Patron von Stufe 2 bis Stufe 10 erhält 0.5%.\n\n• Club-Mitgliedsgebühren:\n  MyHigh5 wendet einen Aufschlag von 10% auf die vom Mitglied ausgewählte Abonnementgebühr an. Von diesem Aufschlag werden 10% an den direkten Patron des Zahlers gezahlt, und 1% werden an jeden indirekten Patron von Stufe 2 bis Stufe 10 gezahlt.\n\n• Website-Sponsoren-Seite Plätze:\n  Für auf der Website-Sponsoren-Seite bezahlte Plätze werden 10% an den Stufe-1-Patron gezahlt, und 1% wird an jeden der Stufe-2-bis-Stufe-10-Patrone gezahlt.",
        question_3: "Was ist der Status eines Gründungsmitglieds?",
        answer_3: "Der Status eines Gründungsmitglieds (MFM) ist eine begrenzte Gelegenheit, die die Kontoverifizierung und die Zahlung einer Beitrittsgebühr von 100$ und einer jährlichen Club-Mitgliedsgebühr von 50$ für die ersten 1.000 MFM erfordert, und eine Beitrittsgebühr von 200$ und eine jährliche Club-Mitgliedsgebühr von 200$ danach. MFM-Plätze werden nicht mehr existieren, sobald die Gesamtzahl der MFM 10.000 erreicht. Gründungsmitglieder nehmen an monatlichen Provisionspools teil, die 10% der Nettoumsätze entsprechen, und einem jährlichen Gewinnpool, der 20% der Gewinne nach Steuern entspricht, zugeteilt basierend auf dem Anteil ihrer verifizierten Empfehlungen der Stufe 1 im Verhältnis zur Gesamtzahl der verifizierten Empfehlungen der Stufe 1.",
        question_4: "Wie kann ich an Wettbewerben teilnehmen?",
        answer_4: "Um an Wettbewerben teilzunehmen, müssen Sie ein kostenloses Konto erstellen, Ihr Profil vervollständigen und Ihre Bewerbung mit Fotos oder Videos gemäß den Anforderungen des Wettbewerbs einreichen. Einige Wettbewerbe können eine KYC-Verifizierung erfordern.",
        question_5: "Sind Wettbewerbe kostenlos?",
        answer_5: "Ja. Die Teilnahme an Wettbewerben ist kostenlos, aber Ihr Konto muss verifiziert sein, da wir Ihren Teilnahmeinhalt mit Ihrer verifizierten Identität abgleichen müssen. Sie müssen Ihr Konto nicht verifizieren, um Kandidaten zu nominieren.",
        question_6: "Wie kann ich meine Einnahmen abheben?",
        answer_6: "Sie können Ihre Einnahmen über Ihre Brieftasche im Dashboard abheben. Zahlungen werden monatlich verarbeitet, mit einem Mindestauszahlungsschwellenwert von 100$. Zahlungsmethoden umfassen Banküberweisung, PayPal oder Kryptowährung."
      },
      download_app: {
        badge: "Mobile App",
        title: "Laden Sie die MyHigh5 App herunter",
        subtitle: "Nehmen Sie an Wettbewerben teil, stimmen Sie ab und verdienen Sie Geld, wo immer Sie sind, mit unserer mobilen App",
        scan_qr: "Zum Herunterladen scannen",
        download_on: "Herunterladen auf",
        app_store: "App Store",
        available_on: "Verfügbar auf",
        google_play: "Google Play",
        access_24_7: "24/7 Zugang",
        free: "Kostenlos"
      }
    },
    footer: {
      description: "Die weltweit beliebteste Wettbewerbsplattform. Nehmen Sie teil, stimmen Sie ab und gewinnen Sie bei aufregenden Wettbewerben.",
      copyright: " 2024 MyHigh5. Alle Rechte vorbehalten.",
      newsletter: {
        title: "Bleiben Sie über neue Wettbewerbe informiert",
        subtitle: "Erhalten Sie die neuesten Nachrichten und Möglichkeiten direkt in Ihren Posteingang.",
        placeholder: "Ihre E-Mail-Adresse",
        subscribe: "Abonnieren",
        terms: "Durch das Abonnieren stimmen Sie unseren Nutzungsbedingungen und unserer Datenschutzrichtlinie zu."
      },
      brand: {
        countries: "In 200+ Ländern verfügbar",
        support: "24/7 Support",
        email: "infos@myhigh5.com"
      },
      quick_links: {
        title: "Schnelle Links",
        about: "Über uns",
        contests: "Wettbewerbe",
        how_it_works: "Wie es funktioniert",
        affiliate: "Partnerprogramm",
        support: "Support"
      },
      categories: {
        title: "Kategorien",
        beauty: "Schönheitswettbewerbe",
        handsome: "Attraktivitätswettbewerbe",
        latest_hits: "Neueste Hits",
        pets: "Haustiere",
        sports_clubs: "Sportvereine",
        no_categories: "Keine Kategorien verfügbar"
      },
      legal: {
        title: "Rechtliches",
        privacy: "Datenschutzrichtlinie",
        terms: "Nutzungsbedingungen",
        cookies: "Cookie-Richtlinie",
        gdpr: "DSGVO-Konformität"
      }
    },
    dashboard: {
      welcome: "Willkommen",
      subtitle: "Entdecken Sie Ihr personalisiertes Dashboard",
      search: {
        placeholder: "Suchen...",
        title: " Suche",
        description: "Finden Sie Wettbewerbe, Teilnehmer, Clubs und Produkte",
        no_results: "Keine Ergebnisse gefunden",
        start_typing: "Beginnen Sie zu tippen, um zu suchen...",
        contest: "Wettbewerb",
        contestant: "Teilnehmer",
        club: "Club",
        product: "Produkt",
        recent_searches: "Letzte Suchanfragen",
        no_history: "Keine letzten Suchanfragen."
      },
      nav: {
        home: "Startseite",
        overview: "Übersicht",
        feed: "Feed",
        contests: "Wettbewerbe",
        groups: "Gruppen",
        my_applications: "Meine Bewerbungen",
        clubs: "Clubs",
        myhigh5: "MyHigh5",
        favorites: "Favoriten",
        search: "Suche",
        pages: "Seiten",
        wallet: "Geldbörse",
        affiliates: "Partner",
        commissions: "Provisionen",
        leaderboard: "Rangliste",
        prize: "Preis",
        shop: "Shop",
        main: "Hauptmenü",
        competitions: "Wettbewerbe",
        business: "Geschäft",
        resources: "Ressourcen",
        account: "Konto",
        settings: "Einstellungen",
        admin: "Verwaltung",
        admin_panel: "Admin-Panel",
        admin_panel_desc: "Plattform verwalten",
        notifications: "Benachrichtigungen",
        notifications_desc: "Alle Ihre Benachrichtigungen anzeigen"
      },
      stats: {
        contests: "Meine Wettbewerbe",
        clubs: "Meine Clubs",
        favorites: "Meine Favoriten",
        points: "Meine Punkte"
      },
      analytics: {
        hello: "Hallo",
        overview: "Hier ist ein Überblick über Ihre Leistung",
        performance: "Leistung",
        affiliates: "Partner",
        total_votes: "Stimmen",
        likes: "Gefällt mir",
        comments: "Kommentare",
        total_views: "Aufrufe",
        reactions: "Reaktionen",
        direct_affiliates: "Direkte Partner",
        total_network: "Gesamtnetzwerk",
        commissions: "Provisionen",
        conversion_rate: "Konversionsrate",
        contest_performance: "Wettbewerbsleistung",
        contest_performance_desc: "Stimmen und Engagement Ihrer Bewerbungen",
        reactions_distribution: "Reaktionen",
        reactions_distribution_desc: "Verteilung nach Typ",
        weekly_activity: "Wöchentliche Aktivität",
        weekly_activity_desc: "Stimmen und Aufrufe diese Woche",
        network_growth: "Netzwerkwachstum",
        network_growth_desc: "Entwicklung Ihrer Partner",
        monthly_commissions: "Monatliche Provisionen",
        monthly_commissions_desc: "Einnahmen durch Ihr Netzwerk",
        active_contests: "Aktive Wettbewerbe",
        best_ranking: "Beste Platzierung",
        engagement: "Engagement",
        this_month: "Diesen Monat",
        total: "Gesamt",
        last_7_days: "7 Tage",
        view_stats: "Statistiken anzeigen",
        statistics: "Statistiken",
        days: {
          monday: "Montag",
          tuesday: "Dienstag",
          wednesday: "Mittwoch",
          thursday: "Donnerstag",
          friday: "Freitag",
          saturday: "Samstag",
          sunday: "Sonntag",
          mon: "Mo",
          tue: "Di",
          wed: "Mi",
          thu: "Do",
          fri: "Fr",
          sat: "Sa",
          sun: "So"
        },
        months: {
          january: "Januar",
          february: "Februar",
          march: "März",
          april: "April",
          may: "Mai",
          june: "Juni",
          july: "Juli",
          august: "August",
          september: "September",
          october: "Oktober",
          november: "November",
          december: "Dezember",
          jan: "Jan",
          feb: "Feb",
          mar: "Mär",
          apr: "Apr",
          may_short: "Mai",
          jun: "Jun",
          jul: "Jul",
          aug: "Aug",
          sep: "Sep",
          oct: "Okt",
          nov: "Nov",
          dec: "Dez"
        }
      },
      wallet: {
        title: "Meine Brieftasche",
        subtitle: "Verwalten Sie Ihre Einnahmen und Transaktionen",
        available_balance: "Verfügbares Guthaben",
        pending_balance: "Ausstehend",
        pending_description: "Guthaben wird validiert",
        total_earnings: "Gesamteinnahmen",
        since_registration: "Seit Registrierung",
        this_month: "diesen Monat",
        history: "Verlauf",
        withdraw: "Abheben",
        add_funds: "Hinzufügen",
        redeem: "Einlösen",
        cards: "Karten",
        recent_transactions: "Letzte Transaktionen",
        all_transactions: "Alle Transaktionen",
        transactions_subtitle: "Vollständiger Verlauf Ihrer Transaktionen",
        see_all: "Alle anzeigen",
        completed: "Abgeschlossen",
        approved: "Genehmigt",
        pending: "Ausstehend",
        failed: "Fehlgeschlagen",
        expired: "Abgelaufen",
        commission: "Provision",
        purchase: "Kauf",
        all: "Alle",
        commissions: "Provisionen",
        purchases: "Käufe",
        filter_by_type: "Nach Typ filtern",
        export: "Exportieren",
        no_transactions: "Keine Transaktionen",
        no_transactions_desc: "Sie haben noch keine Transaktionen",
        pay: "Bezahlen",
        invoice: "Rechnung",
        commission_affiliate: "Partner-Provision",
        welcome_bonus: "Willkommensbonus",
        bank_withdrawal: "Bankabhebung",
        premium_votes: "Premium-Stimmen kaufen"
      },
      affiliates: {
        title: "Partner-Programm",
        subtitle: "Empfehlen und Provisionen verdienen",
        invite: "Einladen",
        total_affiliates: "Gesamt Partner",
        direct_affiliates: "Direkte Partner",
        total_commissions: "Provisionen",
        conversion_rate: "Konversionsrate",
        your_referral_link: "Ihr Empfehlungslink",
        your_referral_links: "Ihre Empfehlungslinks",
        link_register: "Registrierungslink",
        link_home: "Homepage-Link",
        link_contestants: "Wettbewerbe-Seite Link",
        your_code: "Ihr Code",
        copy: "Kopieren",
        copied: "Kopiert!",
        share: "Teilen",
        view_links: "Links anzeigen",
        share_description: "Teilen Sie Ihre Links und verdienen Sie Provisionen für jede Registrierung",
        links_description: "Kopieren und teilen Sie diese Links, um neue Benutzer zu empfehlen",
        your_sponsor: "Ihr Sponsor",
        no_sponsor: "Kein Sponsor",
        commission_tiers: "Provisionsstufen",
        commission_description: "Entdecken Sie unsere 10 Provisionsstufen",
        view_commissions: "Details anzeigen",
        total_potential: "Gesamtpotenzial",
        max_commission: "Maximale Provision über 10 Stufen",
        level: "Stufe",
        direct_referrals: "Direkte Empfehlungen",
        second_level: "Zweite Stufe",
        third_level: "Dritte Stufe",
        your_affiliates: "Ihre Partner",
        see_all: "Alle anzeigen",
        active: "Aktiv",
        joined: "Beigetreten",
        earnings: "Generierte Einnahmen",
        no_affiliates: "Noch keine Partner",
        start_inviting: "Laden Sie Freunde ein um Provisionen zu verdienen",
        invite_friends: "Freunde einladen",
        ten_levels: "10 Provisionsstufen",
        commission: "Provision",
        no_commission: "Keine Provision",
        kyc_pending: "KYC ausstehend",
        commission_rate: "20% auf KYC-Zahlungen",
        commission_structure: "KYC-Provisionsstruktur",
        all_kyc_statuses: "Alle KYC",
        kyc_status_label: "KYC-Status",
        kyc_none: "Nicht gestartet",
        kyc_in_progress: "In Bearbeitung",
        kyc_approved: "Verifiziert",
        kyc_rejected: "Abgelehnt",
        kyc_expired: "Abgelaufen",
        kyc_requires_review: "Überprüfung erforderlich",
        kyc_verified: "KYC Verifiziert",
        direct_referrals: "Direkt (Stufe 1)",
        indirect_referrals: "Indirekt (Stufe 2-10)",
        direct_tooltip_title: "Direkte Empfehlungen",
        direct_tooltip_desc: "Benutzer, die Sie direkt geworben haben (Stufe 1). Sie verdienen 20% Provision auf deren KYC-Zahlungen.",
        indirect_tooltip_title: "Indirekte Empfehlungen",
        indirect_tooltip_desc: "Benutzer, die von Ihren Empfehlungen geworben wurden (Stufen 2-10). Sie verdienen 2% Provision auf deren KYC-Zahlungen.",
        earned: "Verdient",
        total_tooltip_title: "Gesamt Partner",
        total_tooltip_desc: "Gesamtzahl der Personen in Ihrem Affiliate-Netzwerk, alle Stufen zusammen (1 bis 10).",
        active_tooltip_title: "Aktive Partner",
        active_tooltip_desc: "Benutzer mit einem aktiven Konto, die Provisionen generieren können.",
        kyc_verified_tooltip_title: "KYC Verifiziert",
        kyc_verified_tooltip_desc: "Partner, die die Identitätsprüfung erfolgreich abgeschlossen haben (KYC genehmigt).",
        commissions_tooltip_title: "Gesamt Provisionen",
        commissions_tooltip_desc: "Summe aller durch Ihr Affiliate-Netzwerk verdienten Provisionen.",
        col_affiliate_hint: "Informationen über das Mitglied in Ihrem Netzwerk",
        col_level_hint: "Stufe 1 = direkt (20%), Stufen 2-10 = indirekt (2%)",
        col_kyc_hint: "Status der Identitätsprüfung (Provision erhalten wenn genehmigt)",
        col_referrals_hint: "Anzahl der von diesem Partner geworbenen Personen",
        col_earnings_hint: "Provision, die Sie durch diesen Partner verdient haben",
        col_status_hint: "Benutzerkontostatus (aktiv oder inaktiv)",
        levels: "Stufen",
        direct_commission: "Direkte Provision",
        indirect_commission: "Indirekte Provisionen",
        indirect_description: "Verdienen Sie 2% auf jeder Ebene Ihres Netzwerks, bis zur 10. Ebene.",
        cookie_tracking: "Cookie-Tracking: 30 Tage",
        all_affiliates: "Alle Partner",
        affiliates_found: "Partner gefunden",
        search_placeholder: "Nach Name oder E-Mail suchen...",
        all_levels: "Alle Stufen",
        all_statuses: "Alle Status",
        inactive: "Inaktiv",
        affiliate: "Partner",
        referrals_count: "Empfehlungen",
        status: "Status",
        total_referrals: "Gesamt Empfehlungen",
        no_results: "Keine Ergebnisse",
        try_different_filters: "Versuchen Sie andere Filter",
        showing: "Anzeige",
        of: "von",
        pending_invitations: "Ausstehend",
        invite_friend: "Einen Freund einladen",
        invite_description: "Senden Sie eine E-Mail-Einladung, um Ihre Freunde zu empfehlen",
        email_address: "E-Mail-Adresse",
        personal_message: "Persönliche Nachricht",
        message_placeholder: "Hallo! Treten Sie mir auf MyHigh5 bei...",
        send_invitation: "Einladung senden",
        sending: "Wird gesendet...",
        share_link: "Teilen Sie Ihren Link",
        code_label: "Code",
        link_copied: "Link kopiert!",
        invite_sent_success: "Einladung erfolgreich gesendet!",
        invite_error: "Fehler beim Senden der Einladung",
        invite_email_required: "Bitte geben Sie eine E-Mail-Adresse ein",
        pending: "Ausstehend",
        sent_on: "Gesendet am",
        cancel: "Abbrechen",
        invitation_cancelled: "Einladung storniert",
        no_pending: "Keine ausstehenden Einladungen",
        send_invitation_desc: "Senden Sie Einladungen an Ihre Freunde, um sie zu empfehlen",
        copy_error: "Fehler beim Kopieren",
        cancel_error: "Fehler beim Stornieren"
      },
      subtitle: "Verfolgen Sie Ihren Fortschritt, verwalten Sie Ihre Wettbewerbe und erweitern Sie Ihr Netzwerk",
      quick_actions: "Schnellaktionen",
      recent_activity: "Letzte Aktivität",
      no_activity: "Keine aktuelle Aktivität",
      position: {
        title: "Meine Position",
        no_contests: "Keine aktiven Wettbewerbe",
        rank: "Rang",
        points: "Punkte",
        contests: "Schönheitswettbewerb",
        clubs: "Premium-Club",
        affiliates: "Partner",
        status: "Status",
        members: "Mitglieder",
        referrals: "Empfehlungen",
        commissions: "Provisionen",
        active: "Aktiv"
      },
      contests: {
        title: "Wettbewerbe",
        subtitle: "Entdecken Sie Wettbewerbe aus Ihrer Stadt und Ihrem Land und nehmen Sie teil",
        description: "Entdecken Sie die beliebtesten Wettbewerbe und nehmen Sie teil",
        no_contests: "Keine Wettbewerbe verfügbar",
        no_description: "Keine Beschreibung verfügbar",
        all: "Alle",
        nomination: "Nominierung",
        participations: "Teilnahmen",
        filter_level: "Stufe",
        level_city: "Stadt",
        level_country: "Land",
        all_levels: "Alle Stufen",
        nomination_hint: "Nominieren Sie andere zur Teilnahme an Wettbewerben. Stimmen Sie für Teilnehmer ab, die von ihren Fans nominiert wurden.",
        participations_hint: "Nehmen Sie selbst an Wettbewerben teil. Teilnehmer melden sich direkt an, um zu konkurrieren.",
        nominate: "Nominieren",
        edit_nomination: "Bearbeite deine Nominierung",
        edit_participation: "Bearbeite deine Teilnahme",
        edit: "Bearbeiten",
        tooltip_nominate: "Klicken Sie, um an diesem Wettbewerb zu nominieren und Ihren Beitrag einzureichen",
        time_remaining_to_nominate: "Verbleibende Zeit zur Nominierung",
        search_placeholder: "Nach einem Wettbewerb suchen...",
        search_button: "Suchen",
        sort: "Sortieren nach",
        sort_participants: "Meiste Teilnehmer",
        sort_votes: "Meiste Stimmen",
        sort_date: "Neueste",
        sort_name: "Name (A-Z)",
        voting_type: "Abstimmungstyp",
        voting_level_country: "National",
        voting_level_city: "Stadt",
        voting_level_regional: "Regional",
        voting_level_continent: "Kontinental",
        voting_level_global: "Global",
        status: "Status",
        level: "Stufe",
        city: "Stadt",
        country: "National",
        continental: "Kontinental",
        regional: "Regional",
        global: "Global",
        contestants: "Teilnehmer",
        likes: "Mag ich",
        comments: "Kommentare",
        received: "Erhalten",
        participate: "Teilnehmen",
        contest_type: {
          beauty: "Schönheit",
          handsome: "Hübscher",
          latest_hits: "Neueste Hits",
          talent: "Talent",
          photography: "Fotografie",
          fitness: "Fitness",
          fashion: "Mode",
          music: "Musik",
          dance: "Tanz",
          cooking: "Kochen",
          art: "Kunst",
          comics: "Comics",
          other: "Andere"
        },
        men: "Männer",
        women: "Frauen",
        add_favorite: "Zu Favoriten hinzufügen",
        remove_favorite: "Aus Favoriten entfernen",
        added_to_favorites: "Zu Favoriten hinzugefügt",
        removed_from_favorites: "Aus Favoriten entfernt",
        open: "Offen",
        open_for_candidacy: "Offen für Bewerbungen",
        closed: "Geschlossen",
        submission_closed: "Die Anmeldungen sind für diesen Wettbewerb geschlossen.",
        submission_closed_message: "Die Einreichungsfrist ist abgelaufen.",
        no_active_rounds: "Derzeit gibt es keine aktiven Runden, die Einreichungen akzeptieren.",
        description: "Beschreibung",
        requirements: "Anforderungen",
        kyc_required: "Identitätsverifizierung",
        kyc_required_description: "Nur Teilnehmer mit verifizierter Identität können an diesem Wettbewerb teilnehmen",
        visual_verification: "Foto von Ihnen erforderlich",
        visual_verification_description: "Ein Foto von Ihnen ist erforderlich, um an diesem Wettbewerb teilzunehmen",
        voice_verification: "Stimmverifizierung",
        voice_verification_description: "Stimmverifizierung ist erforderlich, um an diesem Wettbewerb teilzunehmen",
        brand_verification: "Verifizierte Marke",
        brand_verification_description: "Nur verifizierte Marken können an diesem Wettbewerb teilnehmen",
        content_verification: "Originalinhalt erforderlich",
        content_verification_description: "Nur Originalinhalt ist zur Teilnahme an diesem Wettbewerb erlaubt",
        gender_restriction: "Geschlechtsbeschränkung",
        gender_restriction_female_description: "Nur weibliche Teilnehmerinnen können an diesem Wettbewerb teilnehmen",
        gender_restriction_male_description: "Nur männliche Teilnehmer können an diesem Wettbewerb teilnehmen",
        age_restriction: "Altersbeschränkung",
        age_restriction_description: "Nur Teilnehmer innerhalb des angegebenen Altersbereichs können teilnehmen",
        tooltip_info: "Wettbewerbsdetails und Anforderungen anzeigen",
        tooltip_time_remaining: "Verbleibende Zeit vor Ende des Wettbewerbs",
        tooltip_gender_restriction_female: "Dieser Wettbewerb ist nur für Frauen",
        tooltip_gender_restriction_male: "Dieser Wettbewerb ist nur für Männer",
        tooltip_level_city: "Wettbewerb auf Stadtebene",
        tooltip_level_country: "Wettbewerb auf nationaler Ebene",
        tooltip_level_regional: "Wettbewerb auf regionaler Ebene",
        tooltip_level_continental: "Wettbewerb auf kontinentaler Ebene",
        tooltip_level_global: "Wettbewerb auf globaler Ebene",
        tooltip_open: "Die Anmeldungen sind derzeit geöffnet. Sie können an diesem Wettbewerb teilnehmen.",
        tooltip_contestants: "Anzahl der Teilnehmer an diesem Wettbewerb",
        tooltip_votes: "Gesamtzahl der erhaltenen Stimmen",
        tooltip_participate: "Klicken Sie, um an diesem Wettbewerb teilzunehmen und Ihren Beitrag einzureichen",
        tooltip_view_contestants: "Alle Teilnehmer dieses Wettbewerbs anzeigen",
        tooltip_view_contestants_closed: "Der Wettbewerb ist geschlossen. Teilnehmer des Wettbewerbs anzeigen",
        tooltip_view_contestants_cannot_participate: "Sie können derzeit nicht teilnehmen. Teilnehmer des Wettbewerbs anzeigen",
        tooltip_closed: "Der Wettbewerb ist geschlossen. Anmeldungen werden nicht mehr angenommen.",
        tooltip_voting_open: "Die Abstimmung ist derzeit geöffnet. Sie können für Teilnehmer abstimmen.",
        tooltip_rank: "Rangliste in diesem Wettbewerb",
        tooltip_author: "Teilnehmerprofil anzeigen",
        tooltip_votes_author: "Erhaltene Stimmen. Bewegen Sie die Maus, um die Liste der Wähler zu sehen.",
        gender_restriction: "Geschlechtsbeschränkung",
        age_restriction: "Altersbeschränkung",
        years: "Jahre",
        contest_info: "Wettbewerbsinformationen",
        contest_dates: "Wettbewerbsdaten",
        submission_start: "Einreichungsbeginn",
        submission_end: "Einreichungsende",
        voting_start: "Abstimmungsbeginn",
        participant_type: "Teilnehmertyp",
        participant_individual: "Einzelperson",
        participant_pet: "Haustier",
        participant_club: "Verein",
        participant_content: "Inhalt",
        male_only: "Nur Männer",
        female_only: "Nur Frauen",
        max_favorites: "5 Favoriten max",
        favorite_limit_reached: "Favoritenlimit erreicht",
        top_participants: "Top Teilnehmer",
        top_5_description: "Die 5 besten Teilnehmer des Wettbewerbs",
        view: "Anzeigen",
        contestant: "Teilnehmer",
        view_contestants: "Teilnehmer anzeigen",
        view_all_contestants: "Alle Teilnehmer anzeigen",
        top_contestants: "Top Teilnehmer",
        time_remaining: "Verbleibende Zeit",
        time_remaining_to_participate: "Verbleibende Zeit zur Teilnahme",
        time_unit_days: "T",
        time_unit_hours: "Std",
        time_unit_minutes: "Min",
        time_unit_seconds: "Sek",
        candidacy_ends: "Ende der Bewerbungen",
        participation_ongoing: "Die Bewerbungen sind noch offen",
        reply: "Antworten",
        reply_placeholder: "Eine Antwort schreiben...",
        show_replies: "{count} Antwort(en) anzeigen",
        hide_replies: "{count} Antwort(en) ausblenden",
        like_added: "Gefällt mir hinzugefügt",
        like_removed: "Gefällt mir entfernt",
        comment_added: "Kommentar hinzugefügt",
        reply_added: "Antwort hinzugefügt",
        vote: "Abstimmen",
        view_details: "Details Anzeigen",
        already_voted: "Bereits abgestimmt",
        cannot_vote: "Sie können nicht für diesen Teilnehmer abstimmen",
        owner_cannot_vote: "Eigentümer, kann nicht abstimmen",
        own_cannot_vote: "Eigene Kandidatur, kann nicht abstimmen",
        votes: "Stimmen",
        shares: "Geteilt",
        submission: "Einreichung",
        voting: "Abstimmung",
        start: "Start",
        end: "Ende",
        add_to_favorites: "Zu Favoriten hinzufügen",
        remove_from_favorites: "Aus Favoriten entfernen",
        reaction_added: "Reaktion hinzugefügt",
        reaction_removed: "Reaktion entfernt",
        no_reactions: "Keine Reaktionen",
        no_votes: "Keine Stimmen",
        no_favorites: "Keine Favoriten",
        more: "mehr",
        loading: "Wird geladen...",
        votes: "Stimmen",
        favorites: "Favoriten",
        points: "Punkte",
        share: "Teilen",
        share_title: "Diesen Teilnehmer teilen",
        share_description: "Teilen Sie diesen Teilnehmer mit Ihren Freunden und Ihrem Netzwerk",
        share_link_label: "Teilungslink",
        copy: "Kopieren",
        copied: "Kopiert",
        share_natively: "Nativ teilen",
        search_contestant: "Nach einem Teilnehmer suchen...",
        filtered_by_country: "Gefiltert nach Ihrem Land",
        no_contestants: "Noch keine Teilnehmer",
        no_contestants_found: "Keine Teilnehmer gefunden",
        like: "Gefällt mir",
        love: "Ich liebe es",
        wow: "Wow",
        dislike: "Gefällt mir nicht",
        favorite: "Favorit",
        comments_description: "Teilen Sie Ihre Gedanken zu diesem Teilnehmer",
        add_comment_placeholder: "Kommentar hinzufügen...",
        sending: "Wird gesendet...",
        send: "Senden",
        no_comments: "Noch keine Kommentare",
        cancel: "Abbrechen",
        mention_hint: "Tippen Sie @, um jemanden zu erwähnen",
        edit: "Bearbeiten",
        delete: "Löschen",
        vote_error: "Fehler beim Abstimmen. Bitte versuchen Sie es erneut.",
        voting_not_open: "Die Abstimmung ist für diesen Wettbewerb noch nicht geöffnet.",
        already_voted_error: "Bereits abgestimmt.",
        cannot_vote_own: "Sie können nicht für Ihre eigene Kandidatur abstimmen.",
        vote_success: "Stimme erfolgreich registriert!",
        vote_replaced: "Stimme erfolgreich ersetzt!",
        my_votes: "Meine Stimmen",
        no_votes_yet: "Stimmen Sie für Ihre Lieblingskandidaten!",
        replace_vote_title: "Stimme ersetzen",
        replace_vote_message: "Sie haben bereits 5 Stimmen. Möchten Sie ersetzen",
        replace_vote_position: "(5. Position, 1 Punkt) durch diesen Teilnehmer?",
        replace_vote_confirm: "Ersetzen",
        max_votes_reached: "Sie haben die maximale Anzahl von 5 Stimmen erreicht",
        empty_slot: "Leerer Platz",
        votes_remaining: "{n} Stimme(n) verbleibend",
        drag_to_reorder: "Ziehen zum Neuordnen",
        vote_gender_restriction_male: "Dieser Wettbewerb ist für männliche Teilnehmer reserviert. Nur weibliche Teilnehmerinnen können abstimmen.",
        vote_gender_restriction_female: "Dieser Wettbewerb ist für weibliche Teilnehmerinnen reserviert. Nur männliche Teilnehmer können abstimmen.",
        vote_gender_not_set: "Ihr Profil enthält keine Geschlechtsangabe. Bitte vervollständigen Sie Ihr Profil, um an diesem Wettbewerb abstimmen zu können.",
        gender: "Geschlecht",
        age: "Alter",
        years: "Jahre",
        country: "Land",
        city: "Stadt",
        bio: "Biografie",
        rank: "Rang",
        votes: "Stimmen",
        male: "Männlich",
        female: "Weiblich",
        report: "Melden",
        reactions: "Reaktionen",
        you_reacted: "Sie haben reagiert",
        no_reactions: "Noch keine Reaktionen",
        people_reacted: "Personen haben reagiert",
        be_first_to_react: "Seien Sie der Erste, der reagiert",
        participant: "Teilnehmer",
        rank: "Rang",
        reaction: "Reaktion",
        my_applications: {
          title: "Meine Bewerbungen",
          description: "Sehen Sie Ihre Bewerbungen und Ihre Platzierung",
          no_applications: "Sie haben noch keine Bewerbungen",
          browse_contests: "Wettbewerbe durchsuchen",
          status: "Status",
          status_pending: "Ausstehend",
          status_approved: "Genehmigt",
          status_rejected: "Abgelehnt",
          rank: "Platzierung",
          view_details: "Details Anzeigen",
          view_page: "Seite Anzeigen",
          edit_not_available: "Bearbeitung für diesen Wettbewerb nicht verfügbar",
          delete_not_available: "Löschung für diesen Wettbewerb nicht verfügbar",
          delete_confirm_message: "Sind Sie sicher, dass Sie diese Bewerbung löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden.",
          details: "Details",
          statistics: "Statistiken",
          total_shares: "Gesamtanteile",
          shares_by_platform: "Anteile nach Plattform",
          no_shares: "Noch keine Anteile",
          contest: "Wettbewerb",
          date: "Datum",
          media: "Medien",
          no_title: "Kein Titel",
          user: "Benutzer",
          media_alt: "Medium",
          video_alt: "Video"
        },
        participation_form: {
          title: "Am Wettbewerb teilnehmen",
          description: "Wählen Sie Ihr bestes Foto oder Video aus, um an diesem Wettbewerb teilzunehmen",
          edit_title: "Kandidat bearbeiten",
          edit_description: "Aktualisiere deine Einreichungsdetails",
          nominate_title: "Kandidat nominieren",
          nominate_description: "Importiere dein Video von YouTube, TikTok, Instagram, Snapchat oder Facebook",
          select_media: "Wählen Sie Ihre Medien",
          drag_drop: "Ziehen Sie Ihre Datei hierher",
          file_info: "oder klicken Sie zum Auswählen (Bilder: JPG, PNG, GIF | Videos: MP4, WebM | Max: 100MB)",
          submit: "Meine Bewerbung einreichen",
          success: "Ihre Bewerbung wurde erfolgreich eingereicht. Sie wird von unserem Team überprüft.",
          success_title: "✅ Bewerbung erfolgreich eingereicht!",
          success_edit: "Ihre Bewerbung wurde erfolgreich aktualisiert.",
          already_participating: "ℹ️ Sie haben bereits eine Bewerbung für diesen Wettbewerb eingereicht. Sie können nur eine Bewerbung pro Wettbewerb einreichen.",
          edit_participation: "Meine Bewerbung bearbeiten",
          click_add_images: "Klicken Sie, um Bilder hinzuzufügen",
          preparing: "Vorbereitung...",
          checking_files: "Dateien werden überprüft...",
          uploading: "Wird hochgeladen...",
          images_format: "Bilder",
          click_add_video: "Klicken Sie, um ein Video hinzuzufügen",
          video_format: "Video",
          cancel: "Abbrechen",
          error: {
            no_media_selected: "Bitte wählen Sie eine Datei",
            invalid_file_type: "Nicht unterstützter Dateityp",
            file_too_large: "Datei ist zu groß (max 100MB)",
            contest_not_found: "Wettbewerb nicht gefunden",
            submit_error: "Fehler beim Einreichen der Bewerbung",
            gender_restriction_male: "Dieser Wettbewerb ist nur für männliche Teilnehmer reserviert.",
            gender_restriction_female: "Dieser Wettbewerb ist nur für weibliche Teilnehmerinnen reserviert.",
            gender_not_set: "Ihr Profil enthält keine Geschlechtsangabe. Bitte vervollständigen Sie Ihr Profil, um an diesem Wettbewerb teilzunehmen.",
            already_submitted: "Sie haben bereits eine Bewerbung für diesen Wettbewerb eingereicht.",
            submission_closed: "Die Anmeldungen sind für diesen Wettbewerb geschlossen.",
            deadline_passed: "Die Einreichungsfrist ist abgelaufen."
          }
        }
      },
      favorites: {
        title: "Meine Favoriten",
        description: "Zeigen Sie Ihre Lieblingswettbewerbe und Kandidaten an",
        contests_tab: "Wettbewerbe",
        contestants_tab: "Kandidaten",
        no_favorite_contests: "Sie haben noch keine Lieblingswettbewerbe",
        no_favorite_contestants: "Sie haben noch keine Lieblingskandidaten"
      },
      myhigh5: {
        title: "MyHigh5",
        description: "Die 5 Teilnehmer, für die Sie gestimmt haben",
        hint: "Ihre erste Stimme wird an Position 1 angezeigt und Ihre neueste Stimme an Position 5. Sie können für maximal 5 Teilnehmer abstimmen.",
        no_votes: "Keine Stimmen",
        no_votes_description: "Sie haben noch für keine Teilnehmer gestimmt. Erkunden Sie Wettbewerbe, um abzustimmen!",
        explore_contests: "Wettbewerbe erkunden",
        explore_more: "Mehr Wettbewerbe erkunden",
        remaining_votes: "Sie können noch für {count} weitere(n) Teilnehmer abstimmen",
        votes_label: "Stimmen",
        hint_dnd: "Ziehen und ablegen, um Ihre Stimmen neu zu ordnen. Der 1. erhält 5 Punkte, der 2. 4 Punkte, der 3. 3 Punkte, der 4. 2 Punkte und der 5. 1 Punkt. Die Stimmen sind auf 5 pro Saison begrenzt.",
        rank: "Rang",
        points: "Punkte",
        contestant: "Teilnehmer",
        location: "Standort",
        total_votes: "Gesamtstimmen",
        vote_date: "Abstimmungsdatum",
        order_saved: "Reihenfolge gespeichert!",
        order_error: "Fehler beim Speichern",
        points_legend: "Punktesystem",
        points_label: "Punkte",
        active_tab: "Aktiv",
        history_tab: "Verlauf",
        no_history: "Kein Verlauf",
        no_history_description: "Sie haben noch keinen Abstimmungsverlauf.",
        inactive: "Beendet"
      },
      leaderboard: {
        title: "Sponsor-Rangliste",
        subtitle: "Die 10 besten Sponsoren mit den meisten direkten Empfehlungen",
        mfm_subtitle: "Die 10 besten MFM-Sponsoren mit den meisten direkten Empfehlungen, die MFM gekauft haben",
        regular_tab: "Allgemeine Rangliste",
        mfm_tab: "MFM-Rangliste",
        referrals: "Empfehlungen",
        benefit: "Vorteil",
        champion: "Champion",
        no_data: "Keine Sponsoren gefunden",
        info_title: "Wie funktioniert die Rangliste?",
        info_description: "Die Rangliste basiert auf der Anzahl der direkten Empfehlungen (Stufe 1), die jeder Sponsor hat. Je mehr direkte Empfehlungen Sie haben, desto höher ist Ihre Position in der Rangliste."
      }
    },
    contestant_detail: {
      about: "Über",
      gallery: "Galerie",
      photos: "Fotos",
      images: "Bilder",
      videos: "Videos",
      votes: "Stimmen",
      rank: "Rang",
      contest_info: "Wettbewerb",
      candidate_info: "Eintrag",
      title: "Titel",
      participants: "Teilnehmer",
      registered_on: "Registriert am",
      status: "Status",
      qualified: "✓ Qualifiziert",
      pending: "⏳ Ausstehend",
      confirm_vote: "Bestätigen Sie Ihre Stimme",
      vote_confirmation: "Sind Sie sicher, dass Sie für abstimmen möchten",
      are_you_sure: "?",
      cancel: "Abbrechen",
      vote: "Abstimmen",
      voted: "Abgestimmt",
      voting: "Abstimmung...",
      cover_image: "Titelbild",
      vote_error: "Fehler beim Abstimmen. Bitte versuchen Sie es erneut.",
      vote_success: "Sie haben erfolgreich abgestimmt! ✨",
      add_reaction: "Reaktion hinzufügen",
      react: "Reagieren",
      like: "Mag ich",
      love: "Liebe",
      wow: "Wow",
      dislike: "Mag ich nicht",
      vote_history: "Abstimmungsverlauf",
      no_votes: "Noch keine Stimmen",
      voted_for: "Abgestimmt für",
      reaction: "Reaktion",
      comment: "Kommentar",
      date: "Datum",
      comments: "Kommentare",
      add_comment: "Kommentar hinzufügen",
      comment_placeholder: "Schreiben Sie Ihren Kommentar...",
      comment_on_photo: "Kommentieren Sie dieses Foto",
      comment_on_video: "Kommentieren Sie dieses Video",
      comment_on_contest: "Kommentieren Sie diesen Wettbewerb",
      no_comments: "Noch keine Kommentare",
      comment_posted: "Kommentar erfolgreich gepostet! ✨",
      comment_error: "Fehler beim Posten des Kommentars",
      comments_count: "Kommentare",
      reply: "Antworten",
      reply_placeholder: "Schreiben Sie Ihre Antwort...",
      like_comment: "Mag ich",
      media_preview: "Medienvorschau",
      close: "Schließen",
      of: "von",
      contestant_label: "Teilnehmer",
      nominator_label: "Nominierender",
      nominated_for: "Nominiert für:",
      contest_rank_label: "Rangliste",
      description_section: "Beschreibung",
      candidacy_id: "Bewerbungs-ID",
      season_label: "Saison",
      entry_fallback_title: "Bewerbung",
      full_description: "Vollständige Beschreibung"
    },
    kyc: {
      verification_required: "Identitätsverifizierung erforderlich",
      verification_required_description: "Um an Wettbewerben teilzunehmen und Ihre Gewinne abzuheben, müssen Sie Ihre Identität verifizieren.",
      start_verification: "Verifizierung starten",
      already_verified: "Identität verifiziert",
      already_verified_description: "Ihre Identität wurde erfolgreich verifiziert. Sie können jetzt alle Funktionen nutzen.",
      verification_in_progress: "Verifizierung läuft",
      verification_in_progress_description: "Ihre Verifizierungsanfrage wird bearbeitet. Wir benachrichtigen Sie, wenn der Prozess abgeschlossen ist.",
      verification_continue_description: "Sie haben eine laufende Verifizierung. Sie können sie fortsetzen oder den Status aktualisieren.",
      continue_verification: "Verifizierung fortsetzen",
      login_required: "Bitte melden Sie sich an, um fortzufahren",
      init_error: "Verifizierung konnte nicht gestartet werden",
      max_attempts_reached: "Maximale Anzahl an Versuchen erreicht",
      max_attempts_description: "Sie haben alle Ihre Verifizierungsversuche aufgebraucht. Bitte kontaktieren Sie unseren Support für Hilfe.",
      max_attempts_can_pay: "Sie haben Ihre kostenlosen Versuche aufgebraucht. Sie können zusätzliche Versuche kaufen, um fortzufahren.",
      buy_attempts: "Zusätzliche Versuche kaufen",
      price_per_attempt: "Preis pro Versuch",
      pay_and_retry: "Bezahlen und erneut versuchen",
      attempts_remaining: "Verbleibende Versuche",
      attempts_used: "Verwendete Versuche",
      verification_status: "Verifizierungsstatus",
      verification_status_description: "Überprüfen Sie den Status Ihrer Identitätsverifizierung",
      verification_rejected: "Verifizierung abgelehnt",
      verification_rejected_description: "Ihre Verifizierungsanfrage wurde abgelehnt. Sie können eine neue Anfrage stellen.",
      rejection_reason: "Ablehnungsgrund",
      submitted_on: "Eingereicht am",
      submit_again: "Erneut versuchen",
      verification_steps: "Wie funktioniert es?",
      step_1_title: "1. Persönliche Informationen",
      step_1_desc: "Geben Sie Ihre grundlegenden persönlichen Daten an",
      step_2_title: "2. Ausweisdokument",
      step_2_desc: "Fotografieren Sie Ihr Ausweisdokument",
      step_3_title: "3. Verifizierungs-Selfie",
      step_3_desc: "Machen Sie ein Selfie, um Ihre Identität zu bestätigen",
      accepted_documents: "Akzeptierte Dokumente",
      doc_passport: "Reisepass",
      doc_id_card: "Personalausweis",
      doc_driving_license: "Führerschein",
      initiating: "Wird gestartet...",
      redirect_notice: "Sie werden zu unserem sicheren Verifizierungspartner weitergeleitet",
      follow_instructions: "Befolgen Sie die folgenden Anweisungen, um Ihre Identitätsverifizierung abzuschließen.",
      secure_verification: "Sichere Verifizierung durch unseren zertifizierten Partner",
      uploaded_documents: "Hochgeladene Dokumente",
      document_front: "Dokumentvorderseite",
      document_back: "Dokumentrückseite",
      selfie: "Selfie",
      steps: "Verifizierungsschritte",
      personal_info: "Persönliche Informationen",
      personal_info_desc: "Geben Sie Ihre persönlichen Daten ein",
      document_info: "Dokumentinformationen",
      document_info_desc: "Geben Sie Ihre Dokumentdetails an",
      review_submit: "Überprüfen und Absenden",
      review_submit_desc: "Überprüfen und senden Sie Ihre Informationen",
      secure: "Ihre Daten sind sicher",
      secure_desc: "Alle Ihre Informationen sind verschlüsselt und nach internationalen Standards geschützt.",
      first_name: "Vorname",
      first_name_placeholder: "Geben Sie Ihren Vornamen ein",
      last_name: "Nachname",
      last_name_placeholder: "Geben Sie Ihren Nachnamen ein",
      date_of_birth: "Geburtsdatum",
      nationality: "Nationalität",
      nationality_placeholder: "Geben Sie Ihre Nationalität ein",
      address: "Adresse",
      address_placeholder: "Geben Sie Ihre vollständige Adresse ein",
      document_type: "Dokumenttyp",
      passport: "Reisepass",
      national_id: "Personalausweis",
      drivers_license: "Führerschein",
      document_number: "Dokumentnummer",
      document_number_placeholder: "Geben Sie Ihre Dokumentnummer ein",
      issuing_country: "Ausstellungsland",
      issuing_country_placeholder: "Geben Sie das Land ein, das Ihr Dokument ausgestellt hat",
      document_upload_next: "Dokumentupload kommt als nächstes",
      document_upload_next_desc: "Im nächsten Schritt laden Sie Fotos Ihres Dokuments (Vorder- und Rückseite) und ein Selfie hoch.",
      processing_time: "Verarbeitungszeit",
      processing_time_desc: "Ihre Verifizierung wird innerhalb von 24-48 Stunden bearbeitet. Sie erhalten eine E-Mail-Benachrichtigung nach Abschluss.",
      submission_success: "Verifizierung erfolgreich eingereicht! Wird weitergeleitet...",
      submit_verification: "Verifizierung Absenden",
      errors: {
        first_name_required: "Vorname erforderlich",
        last_name_required: "Nachname erforderlich",
        date_of_birth_required: "Geburtsdatum erforderlich",
        nationality_required: "Nationalität erforderlich",
        address_required: "Adresse erforderlich",
        document_type_required: "Dokumenttyp erforderlich",
        document_number_required: "Dokumentnummer erforderlich",
        issuing_country_required: "Ausstellungsland erforderlich",
        document_front_required: "Dokumentvorderseite erforderlich",
        document_back_required: "Dokumentrückseite erforderlich",
        selfie_required: "Selfie erforderlich"
      }
    },
    payment: {
      payment_required: "Zahlung erforderlich",
      payment_instructions: "Zahlungsanweisungen",
      payment_description: "Um auf {product} zuzugreifen, leisten Sie bitte eine Zahlung von {amount}.",
      send_exact_amount: "Senden Sie genau {amount} an die untenstehende Adresse.",
      kyc_verification: "KYC-Verifizierung",
      efm_membership: "EFM-Mitgliedschaft",
      kyc_description: "Identitätsprüfung zur Teilnahme an Wettbewerben",
      efm_description: "Werden Sie EFM-Gründungsmitglied",
      validity_one_year: "Gültigkeit: 1 Jahr pro Einheit",
      unit: "Einheit",
      quantity: "Menge",
      total: "Gesamt",
      choose_method: "Wählen Sie Ihre Zahlungsmethode",
      choose_product: "Produkt wählen",
      choose_product_description: "Wählen Sie das Produkt, das Sie kaufen möchten.",
      payment_method: "Zahlungsmethode",
      cryptocurrencies: "Kryptowährungen",
      other_methods: "Andere Methoden",
      card: "Bankkarte",
      bank_transfer: "Banküberweisung",
      network: "Netzwerk",
      amount_to_send: "Zu sendender Betrag",
      receiving_address: "Empfangsadresse",
      bank_details: "Bankverbindung",
      beneficiary: "Begünstigter",
      bank_reference_info: "Geben Sie Ihre E-Mail als Verwendungszweck an, um die Identifizierung zu erleichtern.",
      network_warning: "Stellen Sie sicher, dass Sie den genauen Betrag im richtigen Netzwerk senden. Netzwerkfehler können zu Geldverlust führen.",
      payment_done: "Ich habe die Zahlung geleistet",
      validation_time_info: "Nach Ihrer Zahlung kann die Validierung je nach gewählter Methode einige Minuten bis einige Stunden dauern.",
      min: "Min",
      min_amount: "Mindestbetrag",
      min_amount_error: "Der Mindestbetrag ist {amount}",
      enter_amount: "Betrag eingeben",
      custom_amount: "Benutzerdefinierter Betrag",
      card_coming_soon: "Kartenzahlung bald verfügbar",
      creating_payment: "Zahlung wird erstellt...",
      order_id: "Referenz",
      add_recipients: "Empfänger hinzufügen",
      recipients_description: "Fügen Sie Benutzer hinzu, für die Sie bezahlen möchten",
      method_description: "Wählen Sie Ihre Zahlungsmethode",
      instructions_description: "Senden Sie den genauen Betrag an die angezeigte Adresse",
      recipient: "Empfänger",
      username_or_email: "Benutzername oder E-Mail",
      user_not_found: "Benutzer nicht gefunden",
      product_type: "Produkttyp",
      amount: "Betrag",
      min_100: "Minimum 100 USD",
      add_recipient: "Empfänger hinzufügen",
      recipients_count: "Empfänger",
      confirm_close_title: "Zahlung schließen?",
      confirm_close_description: "Ihr Fortschritt geht verloren. Sind Sie sicher, dass Sie schließen möchten?",
      pay_for_myself: "Für mich bezahlen",
      pay_for_others: "Für andere bezahlen",
      add_other_user: "Anderen Benutzer hinzufügen",
      checking: "Überprüfung...",
      waiting_confirmation: "Zahlung wartet auf Bestätigung...",
      not_received: "Zahlung noch nicht erhalten. Bitte versuchen Sie es erneut.",
      success_title: "Zahlung bestätigt!",
      success_description: "Ihre Zahlung wurde empfangen und bestätigt. Sie können jetzt fortfahren.",
      amount_paid: "Bezahlter Betrag",
      auto_checking: "Automatische Überprüfung aktiv",
      last_check: "Letzte Prüfung",
      waiting_payment: "Warten auf Zahlung...",
      confirming: "Zahlung erkannt, Bestätigung läuft...",
      partially_paid: "Teilzahlung erhalten. Bitte vervollständigen Sie den Betrag.",
      kyc_verification: "KYC-Service",
      mfm_membership: "MFM",
      annual_membership: "Jahresabonnement",
      buy_services: "Dienste kaufen",
      select_for_myself: "Für mich selbst",
      select_service: "Wählen Sie einen Dienst für sich",
      kyc_description: "Identitätsprüfung zur Teilnahme an Wettbewerben",
      mfm_description: "Zugang zum monatlichen (10%) und jährlichen (20%) Einnahmenpool + zufällige Empfehlungen",
      annual_description: "Jährliche Verlängerung des Founding Member Status",
      total_to_pay: "Gesamtbetrag",
      card: "Kreditkarte",
      bank_transfer: "Banküberweisung",
      no_payment_id: "Keine Zahlungs-ID gefunden",
      payment_expired: "Diese Zahlung ist abgelaufen. Bitte erstellen Sie eine neue Zahlung.",
      fetch_error: "Fehler beim Laden der Zahlungsdetails"
    },
    contests: {
      profile_incomplete_title: "Unvollständiges Profil",
      profile_incomplete_message: "Vervollständigen Sie Ihr Profil, um an Wettbewerben teilnehmen zu können.",
      complete_profile: "Vervollständigen",
      kyc_required_title: "Identitätsverifizierung erforderlich",
      kyc_required_message: "Verifizieren Sie Ihre Identität (KYC), um an Wettbewerben teilnehmen zu können.",
      verify_identity: "Verifizieren"
    },
    user: {
      profile: "Profil",
      settings: "Einstellungen",
      kyc: "KYC-Verifizierung",
      subscription: "Abonnement",
      logout: "Abmelden"
    },
    notifications: {
      title: "Benachrichtigungen",
      no_notifications: "Keine Benachrichtigungen",
      mark_all_read: "Alle als gelesen markieren",
      mark_as_read: "Als gelesen markieren",
      view_all: "Alle Benachrichtigungen anzeigen",
      types: {
        system: "System",
        contest: "Wettbewerb",
        compte: "Konto"
      },
      messages: {
        new_vote: "hat für deine Bewerbung gestimmt",
        new_comment: "hat deine Bewerbung kommentiert",
        new_reply: "hat auf deinen Kommentar geantwortet",
        new_like: "hat deinen Kommentar gemocht",
        new_reaction: "hat auf deine Bewerbung reagiert"
      },
      time: {
        just_now: "Gerade eben",
        seconds_ago: "vor ein paar Sekunden",
        minute_ago: "vor einer Minute",
        minutes_ago: "vor {count} Minuten",
        hour_ago: "vor einer Stunde",
        hours_ago: "vor {count} Stunden",
        day_ago: "vor einem Tag",
        days_ago: "vor {count} Tagen",
        week_ago: "vor einer Woche",
        weeks_ago: "vor {count} Wochen",
        month_ago: "vor einem Monat",
        months_ago: "vor {count} Monaten",
        year_ago: "vor einem Jahr",
        years_ago: "vor {count} Jahren"
      }
    },
    pages: {
      contests: {
        badge: "Laufende Wettbewerbe",
        title: "Entdecken Sie unsere Wettbewerbe",
        subtitle: "Nehmen Sie teil, nominieren Sie oder stimmen Sie in spannenden Wettbewerben ab, die vom lokalen zum globalen Level fortschreiten.",
        search_placeholder: "Wettbewerb suchen...",
        filters: {
          all: "Alle",
          city: "Stadt",
          country: "Land",
          regional: "Regional",
          continental: "Kontinental",
          global: "Global"
        },
        stats: {
          active: "Aktive Wettbewerbe",
          participants: "Teilnehmer",
          levels: "Levels"
        },
        all_contests: "Alle Wettbewerbe",
        contests_filter: "Wettbewerbe",
        results: "Ergebnis",
        reset_filters: "Filter zurücksetzen",
        join_community: "Treten Sie der Gemeinschaft bei",
        learn_more: "Mehr erfahren",
        no_results: "Kein Wettbewerb gefunden",
        try_different_filter: "Versuchen Sie einen anderen Filter oder Suchbegriff",
        auth_required_title: "Anmeldung erforderlich",
        auth_required_description: "Sie müssen angemeldet sein, um an Wettbewerben teilzunehmen oder Teilnehmer anzuzeigen.",
        auth_required_benefits_title: "Durch die Anmeldung können Sie:",
        auth_required_benefit_participate: "An Wettbewerben teilnehmen",
        auth_required_benefit_view_contestants: "Teilnehmer anzeigen",
        auth_required_benefit_vote: "Für Ihre Favoriten abstimmen",
        auth_required_benefit_comment: "Kommentieren und interagieren",
        auth_required_login: "Anmelden",
        auth_required_register: "Konto erstellen",
        cta: {
          title: "Bereit teilzunehmen?",
          subtitle: "Erstellen Sie Ihr kostenloses Konto und beginnen Sie noch heute zu konkurrieren!",
          button: "Mein Konto erstellen"
        }
      },
      clubs: {
        title: "Exklusive Fan-Clubs",
        subtitle: "Treten Sie leidenschaftlichen Gemeinschaften bei und greifen Sie auf exklusive Inhalte zu",
        search_placeholder: "Club suchen...",
        features: {
          dsp: "DSP-Zahlung",
          multi_admin: "Multi-Admin",
          affiliate: "Partnerprogramm"
        },
        no_results: "Kein Club gefunden",
        try_different_filter: "Versuchen Sie einen anderen Filter",
        cta: {
          title: "Erstellen Sie Ihren eigenen Club",
          subtitle: "Monetarisieren Sie Ihre Inhalte, verwalten Sie Ihre Community und verdienen Sie durch das Partnerprogramm.",
          feature1: "Sichere Zahlungen über DSP",
          feature2: "Multi-Administrator-Verwaltung",
          feature3: "20% Provision auf Verkäufe",
          button: "Meinen Club erstellen"
        }
      },
      about: {
        title: "Über MyHigh5",
        subtitle: "Die erste ganzheitliche Online-Wettbewerbsplattform, die Talente von der Stadtebene bis zur globalen Bühne entdeckt und präsentiert.",
        mission: {
          title: "Unsere Mission",
          description: "Den Zugang zu Wettbewerben demokratisieren und jedem Talent ermöglichen, auf der Weltbühne zu glänzen."
        },
        values: {
          title: "Unsere Werte",
          subtitle: "Die Prinzipien, die jede unserer Entscheidungen leiten"
        },
        timeline: {
          title: "Unsere Reise"
        },
        team: {
          title: "Unser Team",
          subtitle: "Leidenschaftliche Menschen, die sich Ihrem Erfolg widmen"
        },
        cta: {
          title: "Schließen Sie sich dem MyHigh5-Abenteuer an",
          subtitle: "Werden Sie Teil einer globalen Gemeinschaft von Talenten.",
          button: "Jetzt starten"
        }
      },
      contact: {
        title: "Kontaktieren Sie uns",
        subtitle: "Unser Team ist hier, um zu helfen. Wir antworten normalerweise innerhalb von 24 Stunden.",
        form: {
          title: "Senden Sie uns eine Nachricht",
          name: "Vollständiger Name",
          email: "E-Mail",
          category: "Kategorie",
          subject: "Betreff",
          message: "Nachricht",
          submit: "Nachricht senden"
        },
        faq: {
          title: "Häufig gestellte Fragen"
        },
        hours: {
          title: "Support-Zeiten"
        },
        categories: {
          title: "Wie können wir Ihnen helfen?"
        }
      }
    },
    verification: {
      requirements_title: "Erforderliche Überprüfungen",
      requirements_description: "Dieser Wettbewerb erfordert die folgenden Überprüfungen zur Teilnahme.",
      contest: "Wettbewerb",
      progress: "Fortschritt",
      completed: "Abgeschlossen",
      required: "Erforderlich",
      verify: "Überprüfen",
      proceed: "Fortfahren",
      incomplete_warning: "Vervollständigen Sie alle Überprüfungen, um teilzunehmen.",
      kyc_verification: "KYC-Überprüfung",
      visual_verification: "Visuelle Überprüfung (Selfie)",
      voice_verification: "Stimmüberprüfung",
      selfie: "Verifizierungs-Selfie",
      selfie_with_pet: "Selfie mit Ihrem Haustier",
      selfie_with_document: "Selfie mit Dokument",
      selfie_instructions: "Machen Sie ein klares Foto Ihres Gesichts, gut beleuchtet.",
      selfie_pet_instructions: "Machen Sie ein klares Foto von Ihnen mit Ihrem Haustier.",
      selfie_document_instructions: "Machen Sie ein Foto von Ihnen mit einem sichtbaren Ausweis.",
      voice_instructions: "Nehmen Sie Ihre Stimme für einige Sekunden auf.",
      use_camera: "Kamera verwenden",
      upload_image: "Bild hochladen",
      camera_error: "Kamera nicht erreichbar",
      microphone_error: "Mikrofon nicht erreichbar",
      file_too_large: "Datei ist zu groß",
      file_too_large_with_size: "Datei ist zu groß. Maximal zulässige Größe",
      invalid_file_type: "Ungültiger Dateityp",
      upload_error: "Upload-Fehler",
      capture: "Aufnehmen",
      retake: "Wiederholen",
      confirm: "Bestätigen",
      tap_to_record: "Zum Aufnehmen tippen",
      recording: "Aufnahme läuft...",
      recording_complete: "Aufnahme abgeschlossen",
      play: "Abspielen",
      stop: "Stopp",
      selfie_success: "Selfie erfolgreich gespeichert",
      voice_success: "Sprachaufnahme erfolgreich gespeichert"
    }
  }
}
