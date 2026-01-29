import { gql } from "@apollo/client";

export const GET_ROUNDS_FOR_SELECTOR = gql`
  query GetRoundsForSelector($isActive: Boolean) {
    rounds(isActive: $isActive, limit: 100) {
      id
      name
      status
      isSubmissionOpen
      isVotingOpen
      participantsCount
      votesCount
      topContestants {
        id
        title
        imageUrl
        votesCount
        author {
          username
          avatarUrl
        }
      }
    }
  }
`;

export const GET_ROUNDS_WITH_CONTESTS = gql`
  query GetRoundsWithContests(
    $roundId: Int
    $isActive: Boolean
    $hasVotingType: Boolean
    $country: String
    $continent: String
    $search: String
  ) {
    rounds(
      id: $roundId
      isActive: $isActive
      hasVotingType: $hasVotingType
      filterCountry: $country
      filterContinent: $continent
      searchTerm: $search
    ) {
      id
      name
      isSubmissionOpen
      isVotingOpen
      submissionStartDate
      submissionEndDate
      votingStartDate
      votingEndDate
      participantsCount
      votesCount
      
      contests {
        id
        name
        description
        contestType
        coverImageUrl
        level
        participantsCount
        votesCount
        
        participants {
           id
           votesCount
        }
      }
    }
  }
`; export const GET_CONTEST_DETAILS = gql`
  query GetContestDetails($id: Int!) {
    contest(id: $id) {
      id
      name
      description
      contestType
      coverImageUrl
      level
      entriesCount
      totalVotes
      
      rounds {
        id
        name
        status
        isSubmissionOpen
        isVotingOpen
        submissionStartDate
        submissionEndDate
        votingStartDate
        votingEndDate
      }
      
      votingType {
        id
        name
        votingLevel
      }
      
      contestants {
        id
        userId
        title
        description
        imageMediaIds
        videoMediaIds
        votesCount
        rank
        author {
          username
          fullName
          avatarUrl
          country
          city
        }
      }
    }
  }
`;

export const GET_CONTEST_PARTICIPATION_DETAILS = gql`
  query GetContestParticipationDetails($id: Int!) {
    contest(id: $id) {
      id
      name
      description
      isSubmissionOpen
      submissionStartDate
      submissionEndDate
      
      requiresKyc
      requiresVisualVerification
      requiresVoiceVerification
      requiresBrandVerification
      requiresContentVerification
      participantType
      
      requiresVideo
      maxVideos
      videoMaxDuration
      videoMaxSizeMb
      minImages
      maxImages
      
      verificationVideoMaxDuration
      verificationMaxSizeMb
      
      votingType {
        id
        name
      }
      
      currentUserParticipation {
        id
        userId
        title
        description
        imageMediaIds
        videoMediaIds
        nominatorCity
        nominatorCountry
      }
    }
  }
`;
