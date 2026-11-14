import { useParams } from 'react-router'

export function useGameId(): number {
  const { gameId } = useParams()
  return Number(gameId)
}
