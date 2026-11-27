/**
 * The part of three.js the office uses (P4.0). React Three Fiber's Canvas registers
 * every export of 'three' as a drawable element, which put the whole library into the
 * office's download. vite.config.ts hands React Three Fiber this module instead.
 *
 * Two lists: what React Three Fiber itself uses (its renderer, cameras, events and
 * colour settings), and the elements the office draws. Add an element here before
 * drawing it: an element missing from this list fails with "is not part of the THREE
 * namespace".
 */
export {
  // React Three Fiber's own use (dist/*.esm.js, three 0.187.0, R3F 9.8.2)
  ACESFilmicToneMapping,
  BasicShadowMap,
  Clock,
  Color,
  ColorManagement,
  Layers,
  LinearSRGBColorSpace,
  NoToneMapping,
  Object3D,
  OrthographicCamera,
  PCFShadowMap,
  PCFSoftShadowMap,
  PerspectiveCamera,
  RGBAFormat,
  Raycaster,
  SRGBColorSpace,
  Scene,
  ShaderMaterial,
  UnsignedByteType,
  VSMShadowMap,
  Vector2,
  Vector3,
  WebGLRenderer,
  // What the office draws
  AmbientLight,
  BoxGeometry,
  CylinderGeometry,
  DirectionalLight,
  Group,
  IcosahedronGeometry,
  Mesh,
  MeshStandardMaterial,
} from 'three'
