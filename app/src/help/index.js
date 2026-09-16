// Per-screen help copy, kept out of the components so it can be reviewed as prose.
import screens from './screens.json'

export const HELP = screens
export const helpFor = (screen, map = HELP) => (screen ? map[screen] || null : null)
export default HELP
