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

export const GET_CONTESTS_BY_ROUND = gql`
  query GetContestsByRound(
    $roundId: Int!
    $skip: Int
    $limit: Int
    $contestType: String
    $hasVotingType: Boolean
  ) {
    contests(
      roundId: $roundId
      skip: $skip
      limit: $limit
      contestType: $contestType
      hasVotingType: $hasVotingType
    ) {
      id
      name
      description
      contestType
      coverImageUrl
      isActive
      level
      entriesCount
      totalVotes
      
      rounds {
        id
        status
        isSubmissionOpen
        isVotingOpen
        currentUserParticipated
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
        
        contestants {
           id
           votesCount
        }
      }
      
      votingType {
        id
        name
        votingLevel
      }
    }
  }
`;
